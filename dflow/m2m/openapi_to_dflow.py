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

class RestVerb(str, Enum):
    get = 'GET'
    post = 'POST'
    put = 'PUT'
    delete = 'DELETE'
    update = 'UPDATE'

def is_supported_verb(verb: str) -> bool:
    return verb.upper() in RestVerb._value2member_map_

class Parameter(BaseModel):
    name: str
    description: Union[str,None] = None
    location: str
    required: bool
    ptype: str
    schema: Union[str,None] = None

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
            current_path = f"{parent_path}" if parent_path else ''

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
    # """
    # Extracts request parameters from the given list based on the specified location, 
    # handling complex types like objects and arrays.

    # :param params: The list of parameters to extract from.
    # :param param_location: The location to filter parameters by (e.g., "query", "header").
    # :param model: The entire OpenAPI model for reference resolution.
    # :return: A list of extracted Parameter objects or None if none found.
    # """
    extracted_params = []
    # for param in params:
    #     if param['in'] == param_location:
    #         if '$ref' in param.get('schema', {}):
    #             resolved_schema = resolve_reference(param['schema']['$ref'], model)
    #             param_type = resolved_schema.get('type', 'object')
    #             if param_type == 'object':
    #                 properties = resolved_schema.get('properties', {})
    #                 for prop_name, prop_schema in properties.items():
    #                     extracted_params.append(Parameter(
    #                         name=prop_name,
    #                         description=prop_schema.get('description'),
    #                         location=param_location,
    #                         required=prop_schema.get('required', False),
    #                         ptype=prop_schema.get('type', 'object'),
    #                         schema=prop_schema.get('$ref')
    #                     ))
    #             elif param_type == 'array':
    #                 item_schema = resolved_schema.get('items', {})
    #                 if '$ref' in item_schema:
    #                     resolved_item = resolve_reference(item_schema['$ref'], model)
    #                     extracted_params.append(Parameter(
    #                         name=param['name'],
    #                         description=param.get('description'),
    #                         location=param_location,
    #                         required=param.get('required', False),
    #                         ptype='array',
    #                         schema=item_schema['$ref']
    #                     ))
    #                 else:
    #                     extracted_params.append(Parameter(
    #                         name=param['name'],
    #                         description=param.get('description'),
    #                         location=param_location,
    #                         required=param.get('required', False),
    #                         ptype='array',
    #                         schema=None
    #                     ))
    #         else:
    #             extracted_params.append(Parameter(
    #                 name=param['name'],
    #                 description=param.get('description'),
    #                 location=param_location,
    #                 required=param.get('required', False),
    #                 ptype=param.get('schema', {}).get('type', 'string'),
    #                 schema=None
    #             ))
    return extracted_params if extracted_params else None

def extract_request_body(request_body, model):
    if request_body:
        content = request_body.get('content', {})
        return [Parameter(
            name='body',
            description=request_body.get('description'),
            location='body',
            required=True,  # This can be checked more precisely
            ptype='object',
            schema=list(content.keys())[0] if content else None
        )]
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
        if response_code.startswith('2'):
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
                        schema=parameter['schema']
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

def create_name(service: ExtEService, ending=None):
    """ Merges service name with provided ending """
    if ending is None:
        return service.name
    else:
        return service.name + "_" + ending    

def create_service(name, verb, url, port, path, model):
    return ''

def create_trigger(name, description, summary, trigger_type="Intent"):
    return []

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
):
    return ''

def openapi_to_dflow(model: dict):
    "Transforms OpenAPI model to dFlow"
    services = transform_to_ext_eservices(model)
    i = 0
    dflow_eservices = []
    dflow_triggers = []
    dflow_dialogues = []
    for service in services:
        service_name = create_name(service, ending = f"svc_{i}")
        intent_name = create_name(service, ending = f"{i}")
        dialogue_name = create_name(service, ending = f"dlg_{i}")
        
        eservice_definition = create_service(
            name=service_name, 
            verb=service.verb, 
            url=service.baseURL, 
            port=service.port, 
            path=service.path,
            model=model
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
        dflow_triggers.extend(triggers)
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

    