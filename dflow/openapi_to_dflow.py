from intent_generator import *
import spacy
from collections import Counter
from os import path
import jinja2
nlp = spacy.load("en_core_web_sm")


_THIS_DIR = path.abspath(path.dirname(__file__))

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(path.join(_THIS_DIR, 'templates/grammar-templates')))


PRETRAINED_ENTITIES = [
    'PERSON', 'NORP', 'FAC', 'ORG', 'GPE', 'LOC', 'PRODUCT', 'EVENT',
    'WORK_OF_ART', 'LAW', 'LANGUAGE', 'DATE', 'TIME', 'PERCENT', 'MONEY',
    'QUANTITY', 'ORDINAL', 'CARDINAL'
]


def create_name(operationId, ending = None):
   if ending == None:
       return operationId
   else:
       return operationId + '_' + ending
    
def create_service(service_name, verb, host, port, path):
    template = jinja_env.get_template('services.jinja')

    eservice_data = {
        "name": service_name,
        "verb": verb,
        "host": host,
        "port": port,
        "path": path
    }

    output = template.render(eservice=eservice_data)
    return output

def create_trigger(trigger_name, trigger_type="Intent"):
    template = jinja_env.get_template('triggers.jinja')

    triggers = []

    if trigger_type == "Intent":
        phrases = generate_intent_examples(model, tokenizer, operation.summary)
        trigger = {
            "type": trigger_type,
            "name": trigger_name,  
            "phrases": phrases
        }
    elif trigger_type == "Event":
        trigger = {
            "type": trigger_type,
            "name": trigger_name,  
            "uri": f"bot/event/{trigger_name}"
        }

    triggers.append(trigger)

    output = template.render(triggers=triggers)
    return output

def change_type_name(type_name):
    if type_name == "integer": return "int"
    elif type_name == "string": return "str"
    elif type_name == "number": return "float"
    elif type_name == "boolean": return "bool"
    elif type_name == "array": return "list"
    elif type_name == "object": return "dict"


def create_response(model, tokenizer, verb, parameters=[], slots=[], operation_summary=""):
    
    prompt_text = f"""
    Generate a human-like response for the HTTP GET operation in a web service context. Use the given parameters, info slots, and the operation summary to craft a user-friendly message.

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

    inputs = tokenizer.encode(prompt_text, return_tensors="pt")

    outputs = model.generate(
        inputs,
        max_length=500, 
        temperature=0.7,
        do_sample=True,
        num_return_sequences=1,  
        pad_token_id=tokenizer.eos_token_id
    )

    decoded_output = tokenizer.decode(outputs[0], skip_special_tokens=True)
    response = decoded_output.split("Response:")[-1].strip()

    return response


def create_dialogue(dialogue_name, intent_name, service_name, parameters, triggers, verb, current_path, response_properties=None):
    template = jinja_env.get_template('dialogues.jinja')

    form_slots = []
    responses = []

    entities = []
    for phrase in triggers:
        doc = nlp(phrase)
        for ent in doc.ents:
            if ent.label_ in PRETRAINED_ENTITIES:
                entities.append(ent.label_)

    entity_counts = Counter(entities)
    dominant_entity, _ = entity_counts.most_common(1)[0] if entity_counts else (None, None)
    context = "PE:" + dominant_entity if dominant_entity else None

    path_params = []
    query_params = []
    header_params = []
    param_called_list = []
    response_called_list = []

    for param in parameters:
        if param.required:
            param_type = change_type_name(param.ptype)
            if param_type is None:
                break

            prompt_text = f"Please provide the {param.name}"
            slot = {
                "name": param.name,
                "type": param_type,
                "prompt": prompt_text
            }

            if context:
                slot["context"] = context
            form_slots.append(slot)

    if form_slots:
        form_response = {
            "type": "Form",
            "name": create_name(dialogue_name, "form"),
            "slots": form_slots
        }
        responses.append(form_response)
        for param in parameters:

            if not hasattr(param, 'location'):
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


    service_call = service_name + "("
    if path_params:
        service_call += f"path=[{', '.join(path_params)}], "
    if query_params:
        service_call += f"query=[{', '.join(query_params)}], "
    if header_params:
        service_call += f"header=[{', '.join(header_params)}], "
    service_call = service_call.rstrip(", ") + ")"

    

    if verb == "GET":
        if response_properties and current_path in response_properties:
            has_required_response = False

            for prop, prop_data in response_properties[current_path].items():

                if 'type' not in prop_data:
                    continue

                if prop_data.get('required'):
                    has_required_response = True
                    slot_type = change_type_name(prop_data['type'])
                    if slot_type:
                        form_slots.append({
                            "name": prop,
                            "type": slot_type,
                            "service_call": service_call
                        })

            if not has_required_response:
                response_text = create_response(model, tokenizer, verb, param_called_list, response_called_list, operation.summary)
                action_group_response = {
                    "type": "ActionGroup",
                    "name": create_name(dialogue_name, "ag"),
                    "service_call": service_call,
                    "text": response_text
                }
                responses.append(action_group_response)
            else:
                response_called = ','.join([f"{form_response['name']}.{slot['name']}" for slot in form_slots if 'prompt' not in slot])
                response_called_list = response_called.split(',')
                response_text = create_response(model, tokenizer, verb, param_called_list, response_called_list, operation.summary)
                action_group_response = {
                    "type": "ActionGroup",
                    "name": create_name(dialogue_name, "ag"),
                    "text": response_text
                }
                responses.append(action_group_response)
        else:
            action_group_response = {
                "type": "ActionGroup",
                "name": create_name(dialogue_name, "ag"),
                "service_call": service_call,
                "text": response_text
            }
            responses.append(action_group_response)
    elif verb in ["POST", "PUT", "DELETE"]:
        response_text = create_response(model, tokenizer, verb, param_called_list, response_called_list, operation.summary)
        action_group_response = {
            "type": "ActionGroup",
            "name": create_name(dialogue_name, "ag"),
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

    output = template.render(dialogues=[dialogue])
    return output




fetchedApi = fetch_specification("/Users/harabalos/Desktop/petstore.json")
parsed_api = extract_api_elements(fetchedApi)
response_properties = extract_response_properties(fetchedApi)

for endpoint in parsed_api:
    for operation in endpoint.operations:

        triggersList = []  

        service_name = create_name(operation.operationId, "svc")
        intent_name = create_name(operation.operationId)
        dialogue_name = create_name(operation.operationId, "dlg")
        verb = operation.type.upper() 
        host = fetchedApi["host"]
        port = fetchedApi.get("port", None)
        path = endpoint.path

        eservice_definition = create_service(service_name, verb, host, port, path)
        triggers = create_trigger(intent_name)
        triggersList = triggers.split("\n")
        dialogues = create_dialogue(dialogue_name, intent_name, service_name, operation.parameters, triggersList, verb, path, response_properties)

        print(eservice_definition)
        # print(triggers)
        print(dialogues)
        print(operation.summary)