from collections import Counter
import os
import jinja2
import requests
import yaml
import json
import re
import argparse
from dotenv import dotenv_values
from pydantic import BaseModel
from typing import Tuple, Optional, Any, Union, Optional
from enum import Enum
from dflow.utils import llm_invoke, create_user_prompt_message, create_assistant_prompt_message

class RestVerb(str, Enum):
    get = 'GET'
    post = 'POST'
    put = 'PUT'
    delete = 'DELETE'
    update = 'UPDATE'
    patch = 'PATCH'

def is_supported_verb(verb: str) -> bool:
    return verb.upper() in RestVerb._value2member_map_

class Parameter(BaseModel):
    name: str
    description: Union[str,None] = None
    location: str
    required: bool
    ptype: str
    schema: Union[str,None] = None
    media_type: Union[str,None] = None

class Response(BaseModel):
    statusCode: int
    description: Union[str,None] = None
    parameters: Union[list[Parameter],None] = None

class ExtEService(BaseModel):
    name: str
    verb: RestVerb
    host: str
    baseURL: str
    port: Union[int,None] = None
    path: Union[str,None] = None
    summary: Union[str,None] = None
    description: Union[str,None] = None
    operationType: Union[str,None] = None
    queryParams: Union[list[Parameter],None] = None
    pathParams: Union[list[Parameter],None] = None
    bodyParams: Union[list[Parameter],None] = None
    headerParams: Union[list[Parameter],None] = None
    response: Response

class RequestBody(BaseModel):
    description: Union[str,None] = None
    content: Union[str,None] = None

class EService(BaseModel):
    name: str
    verb: str
    host: str
    port: Union[int,None] = None
    path: Union[str,None] = None
    mime: Union[list,None] = None

class Trigger(BaseModel):
    type: str = "Intent" 
    name: str
    phrases: list[str]

class Slot(BaseModel):
    type: str
    name: str
    prompt: Optional[str] = None
    service_call: Optional[str] = None
    response_filter: Optional[str] = None

class DflowResponse(BaseModel):
    type: str
    name: str
    slots: Optional[list[Slot]] = None
    service_call: Optional[str] = None
    text: Optional[str] = None

class Dialogue(BaseModel):
    name: str
    verb: str
    triggers: list[str]
    responses: list[DflowResponse]

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), 'templates')

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
template = jinja_env.get_template('model.dflow.jinja')


def extract_properties_from_schema(schema, model, parent_path="") -> dict:
    """Extract properties from a given schema and return them as a dictionary."""
    extracted_props = []

    if 'properties' in schema:
        for prop, details in schema['properties'].items():
            is_required = prop in schema.get('required', [])
            current_path = f"{parent_path}.{prop}" if parent_path else str(prop)

            prop_details = {
                "name": prop,
                "description": details.get('description'),
                "required": is_required,
                "type": details.get('type', 'unknown'),
                "schema": current_path
            }
            if '$ref' in details:
                ref_schema = resolve_reference(details['$ref'], model)
                nested_props = extract_properties_from_schema(ref_schema, model, current_path)
                extracted_props.extend(nested_props)
            else:
                extracted_props.append(prop_details)
    return extracted_props

def retrieve_server_info(model: dict) -> Tuple[str, str, Union[int, None]]:
    """
    Extracts the server information from the OpenAPI specification.
    Handles simple URLs and server templating cases.

    :param model: The OpenAPI specification as a dictionary.
    :return: Tuple containing host (str), baseURL (str), and port (int or None).
    """
    servers = model.get('servers', [])
    
    if not servers:
        raise ValueError("No servers defined in OpenAPI specification.")

    server = servers[0]
    url = server.get('url', '')

    variables = server.get('variables', {})
    for var, details in variables.items():
        default_value = details.get('default', '')
        url = url.replace(f"{{{var}}}", default_value)

    match = re.match(r'^(https?://)?([^:/]+)(:(\d+))?(/.*)?$', url)    
    if match:
        protocol = match.group(1) or 'http://'
        host = match.group(2)
        port = int(match.group(4)) if match.group(4) else None
        baseURL = protocol + host + (match.group(5) or '')
    else:
        raise ValueError(f"Invalid server URL: {url}")

    return host, baseURL, port


def resolve_reference(ref: str, model: dict) -> Union[dict, None]:
    """
    Resolves a reference  to a schema within the OpenAPI model.
    
    :param ref: The reference string (e.g., "#/components/schemas/Pet").
    :param model: The entire OpenAPI model as a dictionary.
    :return: The resolved schema as a dictionary, or None if not found.
    """
    ref_path = ref.split('/')
    resolved_schema = model
    for part in ref_path[1:]:
        resolved_schema = resolved_schema.get(part, {})
        if not resolved_schema:
            return None
    return resolved_schema

def extract_request_params(params: list, param_location: str, model: dict) -> list[Parameter]:
    """
    Extracts the request parameters for a specific location (e.g., query, path, header).
    
    :param params: A list of parameters from the OpenAPI specification.
    :param param_location: The location of the parameters (query, path, header, etc.).
    :param model: The entire OpenAPI model for resolving references.
    :return: A list of Parameter objects.
    """
    extracted_params = []
    for param in params:
        if param.get('in') == param_location:
            schema = param.get('schema', {})
            param_name = param.get('name')
            param_required = param.get('required', False)
            if '$ref' in schema:
                resolved_schema = resolve_reference(schema['$ref'], model)
                properties = extract_properties_from_schema(resolved_schema, model)
            else:
                properties = extract_properties_from_schema(schema, model)

            if properties:
                for prop in properties:
                    extracted_params.append(
                        Parameter(
                            name=prop['name'] if prop['name'] else param_name,
                            description=prop.get('description', param.get('description')),
                            location=param_location,
                            required=prop['required'] if 'required' in prop else param_required,
                            ptype=prop['type'],
                            schema=prop['schema']
                        )
                    )
            else:
                extracted_params.append(
                    Parameter(
                        name=param_name,
                        description=param.get('description'),
                        location=param_location,
                        required=param_required,
                        ptype=schema.get('type', 'string'),
                        schema=None
                    )
                )
    return extracted_params if extracted_params else []

def extract_request_body(request_body: dict, model: dict) -> Union[Parameter, None]:
    """
    Extracts the request body from the OpenAPI request body section.
    
    :param request_body: The OpenAPI requestBody section as a dictionary.
    :param model: The entire OpenAPI model for resolving references.
    :return: A Parameter object for the request body, or None if not found.
    """
    if not request_body:
        return None
    content = request_body.get('content', {})
    parameters = []
    for content_type, content_details in content.items():
        schema = content_details.get('schema', {})        
        if schema.get('type') == 'array' and 'items' in schema:
            schema = schema['items']
        if '$ref' in schema:
            resolved_schema = resolve_reference(schema['$ref'], model)
            properties = extract_properties_from_schema(resolved_schema, model)
        else:
            properties = extract_properties_from_schema(schema, model)
        for prop in properties:
            parameters.append(
                Parameter(
                    name=prop['name'],
                    description=prop.get('description'),
                    location="body",
                    required=prop['required'],
                    ptype=prop['type'],
                    schema=prop['schema'],
                    media_type=content_type
                )
            )
    if parameters:
        return parameters
    return None

def extract_response(responses: dict, model: dict) -> Union[Response, None]:
    """
    Extracts success (2xx) response from the OpenAPI responses section.
    
    :param responses: The OpenAPI responses section as a dictionary.
    :return: Response object for the 200 status code, or None if not found.
    """
    extracted_responses = {}
    successful_response = None

    for response_code, response_details in responses.items():
        if str(response_code).startswith('2'):
            successful_response = response_code
        extracted_responses[response_code] = []
        content = responses[response_code].get('content', {})
        for content_type, content_details in content.items():
            schema = content_details.get('schema', {})
            if 'type' in schema and schema['type'] == 'array' and 'items' in schema:
                schema = schema['items']
            if '$ref' in schema:
                resolved_schema = resolve_reference(schema['$ref'], model)
                parameters = extract_properties_from_schema(resolved_schema, model)
            else:
                parameters = extract_properties_from_schema(schema, model)
            for parameter in parameters:
                extracted_responses[response_code].append(
                    Parameter(
                        name=parameter['name'],
                        description=parameter['description'],
                        location='response',
                        required=True,
                        ptype=parameter['type'],
                        schema=parameter['schema'],
                        media_type=content_type
                    )
                )
    if not successful_response:
        return None
    return Response(
        statusCode=successful_response,
        description=responses[successful_response].get('description') if successful_response in responses else None,
        parameters=extracted_responses[successful_response] if successful_response in extracted_responses and extracted_responses[successful_response] else None
    )

def transform_to_ext_eservices(model: dict) -> list[ExtEService]:
    services = []
    host, baseURL, port = retrieve_server_info(model)

    for path, methods in model['paths'].items():
        _host, _baseURL, _port = retrieve_server_info({'servers': model['paths'][path].get('servers')}) if model['paths'][path].get('servers') else (host, baseURL, port)
        for verb, operation in methods.items():
            if not isinstance(operation, dict): continue
            _host, _baseURL, _port = retrieve_server_info({'servers': operation.get('servers')}) if operation.get('servers') else (_host, _baseURL, _port)
            _response = extract_response(operation.get('responses', {}), model)
            if not _response:
                continue
            if not is_supported_verb(verb):
                continue
            ext_service = ExtEService(
                name=operation.get('operationId', 'Unknown'),
                verb=RestVerb(verb.upper()),
                host=_host,
                baseURL=_baseURL,
                port=port,
                path=path,
                summary=operation.get('summary'),
                description=operation.get('description'),
                operationType=operation.get('tags', [None])[0],  # Using the first tag as operation type
                queryParams=extract_request_params(operation.get('parameters', []), 'query', model),
                pathParams=extract_request_params(operation.get('parameters', []), 'path', model),
                bodyParams=extract_request_body(operation.get('requestBody', []), model),
                headerParams=extract_request_params(operation.get('parameters', []), 'header', model),
                response=_response
            )
            services.append(ext_service)
    return services

def create_name(name: str, ending=None):
    """ Merges service name with provided ending """
    if ending is None:
        return name
    else:
        return name + "_" + ending    

def create_service(
    model: dict,
    name: str, 
    service: ExtEService, 
) -> EService:
    mime = None
    if service.verb == RestVerb.get:
        if service.response.parameters:
            mime = [parameter.media_type for parameter in service.response.parameters if parameter.media_type]
            mime = list(set(mime))
    else:
        if service.bodyParams:
            mime = [parameter.media_type for parameter in service.bodyParams if parameter.media_type]
            mime = list(set(mime))
    
    if not mime: mime=None
    eservice = EService(
        name=name,
        verb=service.verb,
        host=service.baseURL,
        port=service.port,
        path=service.path,
        mime=mime
    )
    return eservice

def generate_intent_examples(description: Optional[str], summary: Optional[str]):
    if not description and not summary:
        raise ValueError(f"Both provided description and summary are empty!")
    system_prompt = "You are an NLP engineer expert assisting users to create VAs. Each VA scenario calls a specific API that has a description and possibly a summary. Your task is to create a set of 10 diverse intent examples based on the description and summary. The examples should be human-like, varied, and cover different ways the same intent might be expressed. Return a Python list of strings containing only the requested intent examples. Avoid any other text or preamble."
    _prompt = ''
    if description:
        _prompt += f"Description: {description} "
    if summary:
        _prompt += f"Description: {summary} "
    msg = create_user_prompt_message(_prompt)
    response = llm_invoke(system_prompt, messages=[msg])
    response = eval(response)
    return response

def create_trigger(name, description, summary) -> Trigger:
    return Trigger(
        name=name,
        phrases=generate_intent_examples(description, summary)
    )

def create_response(verb: str, request_params: list, response_params: list, summary: str):

    system_prompt = """You are an NLP engineer expert assisting users to create VAs. Each VA scenario calls a specific API and returns its result to the user depending on its summary or description. Your task is to read the API verb, summary, list of request parameters (Parameters) and list of response parameters (Slots) and to create a response message for the user that contains any existing response parameters (Slots). All Slots must be presented to the user. The Slot names must be inside double {{ }} symbols. Return only the requested text. Avoid any other text or preamble. Check the following examples.
Example:
Verb: POST
Parameters: [form1.bookId, form1.bookTitle]
Slots: 
Summary: Submit a new book with its ID and title.
Response: Your book with ID {{form1.bookId}} and title {{form1.bookTitle}} has been added.

Example:
Verb: GET
Parameters: [weather_form.city]
Slots: [weather_form.temperature, weather_form.forecast]
Summary: Retrieves weather information for a given city.
Response: The temperature in {{weather_form.city}} is {{weather_form.temperature}} and the forecast is {{weather_form.forecast}}.
"""
    _prompt = f"""Request:
Verb: {verb}
Parameters: {request_params}
Slots: {response_params}
Summary: {summary}
Response:
"""
    msg = create_user_prompt_message(_prompt)
    response = llm_invoke(system_prompt, messages=[msg], temperature=0.1)
    response = response.replace('\n', ' ')
    response = response.replace('{{', "'")
    response = response.replace('}}', "'")
    return response

def create_dialogue(
    model,
    dialogue_name: str, 
    intent_name: str, 
    service_name: str,
    verb: str,
    response: Response, 
    path: Union[str,None] = None, 
    summary: Union[str,None] = None,
    headerParams: Union[list[Parameter],None] = None,
    queryParams: Union[list[Parameter],None] = None,
    pathParams: Union[list[Parameter],None] = None,
    bodyParams: Union[list[Parameter],None] = None
) -> Dialogue:
    """
    Generate a dialogue configuration for an API operation.

    This function is designed to produce a structured representation of a dialogue
    that can guide a chatbot in handling interactions related to a specific API call.
    The dialogue contains trigger intents, response actions (like forms and action groups),
    and service calls.
    """

    form_slots = []
    responses = []
    parameters = []
    if headerParams:
        parameters.extend(headerParams)
    if queryParams:
        parameters.extend(queryParams)
    if pathParams:
        parameters.extend(pathParams)
    if bodyParams:
        parameters.extend(bodyParams)
    path_params = []
    query_params = []
    header_params = []
    body_params = []
    request_params = []
    form_data_params = []
    response_params = []
    form_response_name = create_name(dialogue_name, ending = "collect_request_params_form")

    for param in parameters:
        if not param.required or not param.location:
            continue
        param_type = change_type_name(param.ptype)
        if param_type is None:
            continue
        # Gather required HRI-collected params/slots to call API 
        form_slots.append(Slot(
            name=param.name,
            type=param_type,
            prompt=f"Please provide the {param.name}"
        ))

        # Craft API call params
        param_called = f"{form_response_name}.{param.name}"
        request_params.append(param_called)    
        if param.location == "path":
            path_params.append(f"{param.name}={param_called}")
        elif param.location == "query":
            query_params.append(f"{param.name}={param_called}")
        elif param.location == "header":
            header_params.append(f"{param.name}={param_called}")
        elif param.location == "body":
            body_params.append(f"{param.name}={param_called}")
  
    # Craft API call
    service_call = service_name + "("
    if path_params:
        service_call += f"path=[{', '.join(path_params)}], "
    if query_params:
        service_call += f"query=[{', '.join(query_params)}], "
    if header_params:
        service_call += f"header=[{', '.join(header_params)}], "
    if body_params:
        service_call += f"body=[{', '.join(body_params)}], "
    if service_call.endswith(", "):
        service_call = service_call[:-2] + ",)"
    else:
        service_call += ")"

    if response.parameters:
        for param in response.parameters:
            slot_type = change_type_name(param.ptype)
            if slot_type:
                form_slots.append(Slot(
                    name=param.name,
                    type=slot_type,
                    service_call=service_call,
                    response_filter=param.schema if param.schema else None
                ))
                
        if form_slots:
            responses.append(DflowResponse(
                type="Form",
                name=form_response_name,
                slots=form_slots
            ))            
        response_called = ','.join([f"{form_response_name}.{slot.name}" for slot in form_slots if slot.prompt])
        response_params = response_called.split(',')
        responses.append(DflowResponse(
            type="ActionGroup",
            name=create_name(dialogue_name, ending = "response_msg_action"),
            text=create_response(verb, request_params, response_params, summary)
        ))
    else:
        if form_slots:
            responses.append(DflowResponse(
                type="Form",
                name=form_response_name,
                slots=form_slots
            ))
        responses.append(DflowResponse(
            type="ActionGroup",
            name=create_name(dialogue_name, ending = "call_api_response_msg_action"),
            service_call=service_call,
            text=create_response(verb, request_params, response_params, summary)
        ))

    return Dialogue(
        name=dialogue_name,
        verb=verb,
        triggers=[intent_name],
        responses=responses
    )

def openapi_to_dflow(model: dict):
    "Transforms OpenAPI model to dFlow"
    services = transform_to_ext_eservices(model)
    i = 0
    dflow_eservices = []
    dflow_triggers = []
    dflow_dialogues = []
    for service in services:
        service_name = create_name(service.name, ending = f"svc_{i}")
        intent_name = create_name(service.name, ending = f"{i}")
        dialogue_name = create_name(service.name, ending = f"dlg_{i}")
        
        eservice_definition = create_service(
            model=model,
            name=service_name, 
            service=service
        )

        triggers = create_trigger(
            name=intent_name, 
            description=service.description,
            summary=service.summary
        )
        if triggers == []:
            continue
        dialogue = create_dialogue(
            model=model,
            dialogue_name=dialogue_name, 
            intent_name=intent_name, 
            service_name=service_name,
            verb=service.verb,
            response=service.response, 
            path=service.path, 
            summary=service.summary,
            headerParams=service.headerParams,
            queryParams=service.queryParams,
            pathParams=service.pathParams,
            bodyParams=service.bodyParams
        )

        dflow_eservices.append(eservice_definition)
        dflow_triggers.append(triggers)
        dflow_dialogues.append(dialogue)
        i += 1

    output = template.render(eservices=dflow_eservices, triggers=dflow_triggers, dialogues=dflow_dialogues)
    return output

def change_type_name(type_name):
    if type_name == "integer": return "int"
    elif type_name == "string": return "str"
    elif type_name == "number": return "float"
    elif type_name == "boolean": return "bool"
    elif type_name == "array": return "list"
    elif type_name == "object": return "dict"

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



if __name__ == '__main__':
    filepath = '/home/nmalamas/github/dflow/openapi.yml'
    with open(filepath, 'r') as file:
        # data = json.load(file)
    # file = open(filepath, 'r')
        data = yaml.safe_load(file)
    file.close()
    result = openapi_to_dflow(data)
    print(result)
    # print(extract_body_parameter_properties(data))

    # data['servers'] = [{
    #     "url": "https://services.issel.ee.auth.gr/",
    #     "description": "ISSEL Services"
    # }]
    # with open(filepath, 'w') as f:
    #     json.dump(data, f)

    