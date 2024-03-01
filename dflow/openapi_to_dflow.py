import spacy
from collections import Counter
from os import path
import jinja2
import requests
import yaml
import json
import re
import argparse
from transformers import AutoModelForCausalLM, AutoTokenizer

NLP = spacy.load("en_core_web_sm")

_THIS_DIR = path.abspath(path.dirname(__file__))

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(path.join(_THIS_DIR, 'templates')))
template = jinja_env.get_template('model.dflow.jinja')

class Llm:
    def __init__(self, method, model_name, model=None, tokenizer=None, llm_api=None, llm_api_auth=None):
        self.method = method
        self.model_name = model_name
        self.model = model
        self.tokenizer = tokenizer
        self.llm_api = llm_api
        self.llm_api_auth = llm_api_auth


class Endpoint:
    def __init__(self, path):
        self.path = path
        self.operations = []


class Operation:
    def __init__(self, type, operationId=None, summary=None, description=None, parameters=None, requestBody=None, responses=None):
        self.type = type
        self.operationId = operationId
        self.summary = summary
        self.description = description
        self.parameters = parameters or []
        self.requestBody = requestBody
        self.responses = responses or []


class Parameter:
    def __init__(self, name, location, required, ptype, description=None, schema=None):
        self.name = name
        self.location = location
        self.description = description
        self.required = required
        self.ptype = ptype
        self.schema = schema


class RequestBody:
    def __init__(self, description=None, content=None):
        self.description = description
        self.content = content


class Response:
    def __init__(self, status_code, description=None):
        self.status_code = status_code
        self.description = description


def fetch_specification(source):
    """
        Fetches an OpenAPI specification from a given source.

        This function retrieves the OpenAPI specification either from a local file or a remote URL.
        It supports both JSON and YAML formats.
    """
    if path.isfile(source):
        with open(source, 'r') as f:
            if source.endswith('.yaml'):
                return yaml.safe_load(f)
            elif source.endswith('.json'):
                return json.load(f)
            else:
                raise ValueError("Invalid file type. Only JSON and YAML are supported.")
    else:
        try:
            response = requests.get(source)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to fetch the specification from {source}. Error: {e}")
            return None
        if source.endswith('.yaml'):
            return yaml.safe_load(response.text)
        elif source.endswith('.json'):
            return json.loads(response.text)
        else:
            raise ValueError("Invalid URL type. Only JSON and YAML are supported.")


def extract_properties_from_schema(schema, api_specification):
    """Extract properties from a given schema."""
    current_details = {}
    if 'properties' in schema:
        for prop, details in schema['properties'].items():
            is_required = prop in schema.get('required', [])
            if 'type' in details:
                # Standard property with a type
                current_details[prop] = {"type": details['type'], "required": is_required}
            elif '$ref' in details:
                # Property refers to another schema via $ref
                ref_schema = resolve_ref(details['$ref'], api_specification)
                current_details[prop] = {
                    "type": "object",  # since $ref refers to an object in OpenAPI spec
                    "required": is_required,
                    "properties": extract_properties_from_schema(ref_schema,api_specification)
                }
            else:
                current_details[prop] = {"type": 'unknown', "required": is_required}
    return current_details


def resolve_ref(ref, api_specification):
    """Resolve a $ref link to its actual schema definition."""
    parts = ref.split('/')
    definition = api_specification
    for part in parts:
        if part == '#':
            continue  # Skip the root definition signifier
        definition = definition.get(part, {})
    return definition


def extract_response_properties(api_specification):
    """Extract response properties and their types for methods from the OpenAPI specification."""

    response_details = {}
    #Iterate through each path defined in the specification
    for path, operations in api_specification['paths'].items():
        # if 'get' in operations:
        for op in operations:
            if 'responses' in operations[op]:
                response_200 = None
                if '200' in operations[op]['responses']:
                    response_200 = operations[op]['responses']['200']
                elif 200 in operations[op]['responses']:
                    response_200 = operations[op]['responses'][200]
                
                if response_200:
                    if 'schema' in response_200:
                        schema = response_200['schema']
                        response_details[path] = {}
                        if 'type' in schema and schema['type'] == 'array' and 'items' in schema:
                            schema = schema['items']

                        extracted_props = extract_properties_from_schema(schema, api_specification)
                        response_details[path].update(extracted_props)

                        if '$ref' in schema:
                            #Handle schemas that refer to other definitions
                            ref_schema = resolve_ref(schema['$ref'], api_specification)
                            extracted_props = extract_properties_from_schema(ref_schema, api_specification)
                            response_details[path].update(extracted_props)
    return response_details


def extract_body_parameter_properties(api_specification):
    """Extract body parameter properties and their types from the OpenAPI specification."""

    body_param_details = {}
    # Iterate through each path defined in the specification
    for path, operations in api_specification['paths'].items():
        for method, operation in operations.items():  # Adding this loop to check all methods, not just 'get'
            if 'parameters' in operation:
                for param in operation['parameters']:
                    if param.get('in') == 'body':
                        param_name = param.get('name')
                        body_param_details[path] = {}
                        schema = param.get('schema', {})
                        if 'type' in schema and schema['type'] == 'array' and 'items' in schema:
                            schema = schema['items']

                        extracted_props = extract_properties_from_schema(schema, api_specification)
                        body_param_details[path].update(extracted_props)

                        if '$ref' in schema:
                            # Handle schemas that refer to other definitions
                            ref_schema = resolve_ref(schema['$ref'], api_specification)
                            extracted_props = extract_properties_from_schema(ref_schema, api_specification)
                            body_param_details[path].update(extracted_props)
    return body_param_details



def extract_api_elements(api_specification):
    """
        Extract essential API components like endpoints, operations, parameters, request bodies, and responses
        from an OpenAPI specification.
    """

    endpoints = []
    for path, operations in api_specification['paths'].items():
        endpoint = Endpoint(path)

        for operation_type, operation_details in operations.items():
            operationSummary = operation_details.get('summary')
            operationId = operation_details.get('operationId')
            operationdDescription = operation_details.get('description')

            parameters = []
            if 'parameters' in operation_details:
                for parameter_details in operation_details['parameters']:
                    name = parameter_details['name']
                    location = parameter_details['in']
                    description = parameter_details.get('description')
                    required = parameter_details.get('required')
                    ptype = parameter_details.get('type')
                    schema = parameter_details.get('schema')
                    parameter = Parameter(name, location, required, ptype, description, schema)
                    parameters.append(parameter)

            requestBody = None
            if 'requestBody' in operation_details:
                requestBody_details = operation_details['requestBody']
                description = requestBody_details.get('description')
                content = requestBody_details.get('content')
                requestBody = RequestBody(description, content)

            responses = []
            if 'responses' in operation_details:
                for status_code, response_details in operation_details['responses'].items():
                    description = response_details.get('description')
                    response = Response(status_code, description)
                    responses.append(response)

            operation = Operation(operation_type, operationId, operationSummary, operationdDescription, parameters, requestBody, responses)
            endpoint.operations.append(operation)

        endpoints.append(endpoint)
    return endpoints


def generate_intent_examples(llm, operation_summary):
    """Generate human-like examples of how users might express an intent for a given operation summary."""

    prompt_text = f"""
I need diverse examples of how a user might express certain intents related to tasks they want to perform. The examples should be human-like, varied, and cover different ways the same intent might be expressed. Here are a few tasks:

Task: Get user details
Example Intents:
    Can you fetch the details for this user?
    Show me the user's information.
    I'd like to see this user's details.

Task: Create a new user
Example Intents:
    I want to register a new user.
    Can we set up a user profile?
    Let's create a new user account.

Task: Find pet by id
Example Intents:
    Where is my pet?
    Find my pet!
    I've lost my pet, could you locate it?

Task: Upload an image
Example Intents:
    I want to upload this picture.
    Can you assist me in uploading an image?
    Post this image now!

Now, for the following task, please generate intent name and 10 diverse intent examples:

Task: {operation_summary.lower()}
Example Intents:
    """
    temperature = 0.7
    max_tokens = 500
    num_return_sequences = 1

    if llm.method == 'model':
        inputs = llm.tokenizer.encode(prompt_text, return_tensors="pt")

        outputs = llm.model.generate(
            inputs,
            max_length=max_tokens,
            temperature=temperature,
            do_sample=True,
            num_return_sequences=num_return_sequences,
            pad_token_id=llm.tokenizer.eos_token_id
        )
        
        output = llm.model.generate(prompt_text)

        decoded_output = llm.tokenizer.decode(outputs[0], skip_special_tokens=True)
        decoded_output = re.sub(r"(\w)'(\w)", r"\1\\'\2", decoded_output)
        intent_examples_raw = decoded_output.split("Intents:")[-1].strip()
        intent_examples = intent_examples_raw.split('\n')

    elif llm.method == 'api':
        
        headers = {
            "Authorization":f"{llm.llm_api_auth}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": {
                "prompt": prompt_text,
                "sampling_params": {
                "max_tokens": max_tokens,
                "n": num_return_sequences,
                "temperature": temperature
                }
            }
        }

        response = requests.post(llm.llm_api, headers=headers, json=payload)
        response = json.loads(response.text)['output']
        intent_examples = response.split('\n')

    elif llm.method == 'cli':
        intent_examples = [
            'Dummy int 1: Can you fetch the details for this user?',
            'Dummy int 2: Show me the user\'s information.',
            'Dummy int 3: I\'d like to see this user\'s details.'
        ]

    clean_intent_examples = [example.split(')')[-1].strip() for example in intent_examples if example.strip()]

    return clean_intent_examples


def create_name(operation_details, ending=None):
    if operation_details['operationId']:
        if ending is None:
            return operation_details['operationId']
        else:
            return operation_details['operationId'] + "_" + ending
    else:
        doc = NLP(operation_details.get('description', ''))

        #find verb-noun pairs in the description
        verb_noun_pairs = [(token.head.text, token) for token in doc if token.dep_ in ("dobj")]

        #if verb-noun pairs are found construct operation ID using the first pair
        if verb_noun_pairs:
            verb, noun_token = verb_noun_pairs[0]
            noun_phrase = "".join([w.text.capitalize() for w in noun_token.subtree])
            op_id = f"{verb.capitalize()}{noun_phrase}"
        else:
            # If no verb-noun pairs are found, just use the longest noun phrase
            noun_phrases = [chunk.text for chunk in doc.noun_chunks]
            op_id = "".join([word.capitalize() for word in max(noun_phrases, key=len).split()])

        op_id = op_id[0].lower() + op_id[1:]

        if ending:
            op_id += "_" + ending

        return op_id

def create_service(service_name, verb, host, port, path, api_specification):
    mime = []
    if verb == "GET":
        if 'produces' in api_specification['paths'][path][verb.lower()]:
            mime = api_specification['paths'][path][verb.lower()]['produces']
        elif 'produces' in api_specification:
            mime = api_specification['produces']
    else:
        if 'consumes' in api_specification['paths'][path][verb.lower()]:
            mime = api_specification['paths'][path][verb.lower()]['consumes']
        elif 'consumes' in api_specification:
            mime = api_specification['consumes']
    eservice_data = {
        "name": service_name,
        "verb": verb,
        "host": host,
        "port": port,
        "path": path
    }

    if mime:
        eservice_data['mime'] = mime
    
    return eservice_data

def create_trigger(trigger_name, operation_summary, llm, trigger_type="Intent"):

    triggers = []
    if trigger_type == "Intent":
        phrases = generate_intent_examples(llm, operation_summary)
        trigger = {
            "type": trigger_type,
            "name": trigger_name,
            "phrases": phrases
        }

    triggers.append(trigger)
    return triggers


def change_type_name(type_name):
    if type_name == "integer": return "int"
    elif type_name == "string": return "str"
    elif type_name == "number": return "float"
    elif type_name == "boolean": return "bool"
    elif type_name == "array": return "list"
    elif type_name == "object": return "dict"


def create_response(llm, verb, parameters=[], slots=[], operation_summary=""):
    """Generate a human-like response for a given HTTP operation using a model."""

    prompt_text = f"""
Generate a human-like response for the HTTP operation in a web service context. Use the given parameters, info slots, and the operation summary to craft a user-friendly message.

Example:
Verb: GET
Parameters: [id, name]
Slots: [status]
Operation Summary: Retrieve a user's status by their id and name.
Response: The status of {{name}} with id {{id}} is {{status}}

Example:
Verb: GET
Parameters: []
Slots: []
Operation Summary: Log the user out of the system.
Response: You have been successfully logged out.

Example:
Verb: POST
Parameters: [bookId, bookTitle]
Slots:
Operation Summary: Submit a new book with its ID and title.
Response: Your book with ID {{bookId}} and title "{{bookTitle}}" has been added.

Example:
Verb: PUT
Parameters: [orderId, quantity]
Slots:
Operation Summary: Update the quantity of an order.
Response: Your order {{orderId}} has been updated to a quantity of {{quantity}}.

Example:
Verb: DELETE
Parameters: [photoId]
Slots:
Operation Summary: Remove a photo based on its ID.
Response: The photo with ID {{photoId}} has been deleted.

Given the following HTTP operation, generate a relevant response:

Verb: {verb}
Parameters: {', '.join(parameters)}
Slots: {', '.join(slots)}
Operation Summary: {operation_summary}
Response:
    """
    temperature = 0.7
    max_tokens = 500
    num_return_sequences = 1

    if llm.method == 'model':
        inputs = llm.tokenizer.encode(prompt_text, return_tensors="pt")

        outputs = llm.model.generate(
            inputs,
            max_length=max_tokens,
            temperature=temperature,
            do_sample=True,
            num_return_sequences=num_return_sequences,
            pad_token_id=llm.tokenizer.eos_token_id
        )
        output = llm.model.generate(prompt_text)

        decoded_output = llm.tokenizer.decode(outputs[0], skip_special_tokens=True)
        decoded_output = re.sub(r"(\w)'(\w)", r"\1\\'\2", decoded_output)
        response = decoded_output.split("Response:")[-1].strip()
    elif llm.method == 'api':
        
        headers = {
            "Authorization":f"{llm.llm_api_auth}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": {
                "prompt": prompt_text,
                "sampling_params": {
                "max_tokens": max_tokens,
                "n": num_return_sequences,
                "temperature": temperature
                }
            }
        }

        response = requests.post(llm.llm_api, headers=headers, json=payload)
        response = json.loads(response.text)['output']
    elif llm.method == 'cli':
        response = 'Dummy response: The status of {{name}} with id {{id}} is {{status}}'

    return response


def create_dialogue(
        dialogue_name, 
        intent_name, 
        service_name, 
        parameters, 
        verb, 
        current_path, 
        operation_summary, 
        api_specification, 
        response_properties=None, 
        body_properties = None
    ):
    """
        Generate a dialogue configuration for an API operation.

        This function is designed to produce a structured representation of a dialogue
        that can guide a chatbot in handling interactions related to a specific API call.
        The dialogue contains trigger intents, response actions (like forms and action groups),
        and service calls.
    """

    form_slots = []
    responses = []
    response_text = ""
    path_params = []
    query_params = []
    header_params = []
    body_params = []
    param_called_list = []
    form_data_params = []
    response_called_list = []

    for param in parameters:
        if param.required:
            if param.location == "body":
                body_props = body_properties[current_path]
                for prop_name, prop_data in body_props.items():
                    if prop_data.get('required', False):
                        prop_type = change_type_name(prop_data['type'])
                        prompt_text = f"Please provide the {prop_name}"
                        slot = {
                            "name": prop_name,
                            "type": prop_type,
                            "prompt": prompt_text
                        }

                        form_slots.append(slot)

            else:
                param_type = change_type_name(param.ptype)
                if param_type is None:
                    continue

                prompt_text = f"Please provide the {param.name}"
                slot = {
                    "name": param.name,
                    "type": param_type,
                    "prompt": prompt_text
                }
                form_slots.append(slot)

    form_response = None
    if form_slots:
        form_response = {
            "type": "Form",
            "name": create_name({'operationId': dialogue_name}, ending = "form"),
            "slots": form_slots
        }
        responses.append(form_response)

    for param in parameters:
        if not param.required or not hasattr(param, 'location'):
            continue

        if param.location == "path":
            param_called = f"{form_response['name']}.{param.name}"
            param_called_list.append(param_called)
            path_params.append(f"{param.name}={param_called}")
        elif param.location == "query":
            param_called = f"{form_response['name']}.{param.name}"
            param_called_list.append(param_called)
            query_params.append(f"{param.name}={param_called}")
        elif param.location == "header":
            param_called = f"{form_response['name']}.{param.name}"
            param_called_list.append(param_called)
            header_params.append(f"{param.name}={param_called}")
        elif param.location == "body":
            body_props = body_properties[current_path]
            for prop_name, prop_data in body_props.items():
                if prop_data.get('required', False):
                    prop_called = f"{form_response['name']}.{prop_name}"
                    param_called_list.append(prop_called)
                    body_params.append(f"{prop_name}={prop_called}")
        # elif param.location == "formData":
        #     param_called = f"{form_response['name']}.{param.name}"
        #     param_called_list.append(param_called)
        #     form_data_params.append(f"{param.name}={param_called}")


    service_call = service_name + "("
    if path_params:
        service_call += f"path=[{', '.join(path_params)}], "
    if query_params:
        service_call += f"query=[{', '.join(query_params)}], "
    if header_params:
        service_call += f"header=[{', '.join(header_params)}], "
    if body_params:
        service_call += f"body=[{', '.join(body_params)}], "
    # if form_data_params:
    #     service_call += f"formData=[{', '.join(form_data_params)}], "

    if service_call.endswith(", "):
        service_call = service_call[:-2] + ",)"
    else:
        service_call += ")"

    if response_properties and current_path in response_properties:
        has_required_response = False

        for prop, prop_data in response_properties[current_path].items():
            if 'type' not in prop_data:
                continue

            has_required_response = True
            slot_type = change_type_name(prop_data['type'])
            if slot_type:
                form_slots.append({
                    "name": prop,
                    "type": slot_type,
                    "service_call": service_call
                })

        if not has_required_response:
            response_text = create_response(llm, verb, param_called_list, response_called_list, operation_summary)
            action_group_response = {
                "type": "ActionGroup",
                "name": create_name({'operationId': dialogue_name}, ending = "ag"),
                "service_call": service_call,
                "text": response_text
            }
            responses.append(action_group_response)
        else:
            # Service already called when storing the required response in a slot
            if form_response is None:
                form_response = {
                    "type": "Form",
                    "name": create_name({'operationId': dialogue_name}, ending = "form"),
                    "slots": form_slots
                }
                responses.append(form_response)
            
            response_called = ','.join([f"{form_response['name']}.{slot['name']}" for slot in form_slots if 'prompt' not in slot])
            response_called_list = response_called.split(',')
            response_text = create_response(llm, verb, param_called_list, response_called_list, operation_summary)
            action_group_response = {
                "type": "ActionGroup",
                "name": create_name({'operationId': dialogue_name}, ending = "ag"),
                "text": response_text
            }
            responses.append(action_group_response)
    else:
        response_text = create_response(llm, verb, param_called_list, response_called_list, operation_summary)
        action_group_response = {
            "type": "ActionGroup",
            "name": create_name({'operationId': dialogue_name}, ending = "ag"),
            "service_call": service_call,
            "text": response_text
        }
        responses.append(action_group_response)

    dialogue = {
        "name": dialogue_name,
        "verb": verb,
        "triggers": [intent_name],
        "responses": responses
    }
    return dialogue


def get_title(title):
    ignore_words = [
        "Swagger", "API", "REST", "RESTful", "Service", "Services",
        "Web", "WebAPI", "Endpoint", "Endpoints", "Server", "Application",
        "System", "Interface", "Platform", "Protocol", "Database", "DB",
        "Microservice", "Specification", "OpenAPI", "Resource", "Resources",
        "Network", "Utility", "Utilities", "Toolkit", "Provider", "Hub",
        "Solution", "Solutions", "Package", "Library", "Framework", "Module",
        "Unit", "Component", "Function", "Operation", "Method", "Gateway",
        "Proxy", "Service", "Repository", "Connector", "Plugin", "Add-on",
        "Extension", "Handler", "Driver", "Layer", "Object", "Manager",
        "Runtime", "Session", "Client", "Middleware", "Adapter", "Model",
        "Engine", "Instance", "Protocol", "Suite", "Set", "Collection",
        "Group", "Cluster", "Version", "Edition", "Build"
    ]
    cleaned_title = " ".join([word for word in title.split() if word not in ignore_words])
    return cleaned_title.lower().replace(" ", "_")


def transform(llm, api_path, save_file = None):
    """Transforms the given API specification into a set of eservices, triggers, and dialogues."""

    fetchedApi = fetch_specification(api_path)
    parsed_api = extract_api_elements(fetchedApi)
    response_properties = extract_response_properties(fetchedApi)
    body_properties = extract_body_parameter_properties(fetchedApi)

    eservices = []
    all_triggers = []
    all_dialogues = []

    i = 1
    for endpoint in parsed_api:
        for operation in endpoint.operations:
            if operation.type.upper() == "DELETE":
                continue

            operation_details = {
                'operationId': operation.operationId,
                'description': operation.description
            }

            service_name = create_name(operation_details, ending = f"svc_{i}")
            intent_name = create_name(operation_details, ending = f"{i}")
            dialogue_name = create_name(operation_details, ending = f"dlg_{i}")
            verb = operation.type.upper()
            
            # Give priority to https than http 
            scheme = fetchedApi.get('schemes', ['http'])
            if len(scheme) == 1:
                scheme = scheme[0]
            elif len(scheme):
                if 'https' in scheme:
                    scheme = 'https'
                elif 'http' in scheme:
                    scheme = 'http'
                else:
                    scheme = scheme[0]
            
            host = f"{scheme}://" + fetchedApi["host"]
            port = fetchedApi.get("port", None)
            path = endpoint.path

            eservice_definition = create_service(service_name, verb, host, port, path, fetchedApi)
            triggers = create_trigger(intent_name, operation.description, llm)
            if triggers == []:
                continue
            dialogue = create_dialogue(dialogue_name, intent_name, service_name, operation.parameters, verb, path, operation.summary,fetchedApi, response_properties, body_properties)

            eservices.append(eservice_definition)
            all_triggers.extend(triggers)
            all_dialogues.append(dialogue)
            i += 1

    output = template.render(eservices=eservices, triggers=all_triggers, dialogues=all_dialogues)

    api_title = fetchedApi.get('info', {}).get('title', 'default_name')
    if not save_file:
        title = get_title(api_title)
        save_file = f"{title}.dflow"
    else:
        if save_file.split('.')[-1] != 'dflow':
            save_file = f"{save_file}.dflow"
    
    with open(save_file, 'w') as file:
        file.write(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument("--model", default=None, type=str,
                        help="LLM model for text generation.")
    parser.add_argument("--llm_api", default=None, type=str,
                        help="LLM API endpoint for text generation.")
    parser.add_argument("--llm_api_auth", default=None, type=str,
                        help="Authentication token of LLM API endpoint.")
    parser.add_argument("--openapi_file", default='openapi_example.yaml', type=str,
                        help="JSON or YAML file path of openAPI specification.")
    parser.add_argument("--save_file", default='model.dflow', type=str,
                        help="path of saved dFlow model.")

    args = parser.parse_args()
    
    if args.model:
        model = AutoModelForCausalLM.from_pretrained(args.model, trust_remote_code=True)
        tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
        method = 'model'
    elif args.llm_api:
        model = None
        tokenizer = None
        if not args.llm_api or not args.llm_api_auth:
            print('LLM API endpoint specification not provided')
            exit(1)
        method = 'api'
    else:
        method = 'cli'
        model = None
        tokenizer = None
    
    llm = Llm(method = method, model_name = args.model, model = model, tokenizer = tokenizer, llm_api = args.llm_api, llm_api_auth = args.llm_api_auth)
    transform(llm, args.openapi_file, args.save_file)