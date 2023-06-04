import os.path
import spacy
import requests
import yaml
import json


class Endpoint:
    def __init__(self, path):
        self.path = path
        self.operations = []  # list of Operation objects


class Operation:
    def __init__(self, type, summary=None, description=None, parameters=None, requestBody=None, responses=None):
        self.type = type
        self.summary = summary
        self.description = description
        self.parameters = parameters or []
        self.requestBody = requestBody
        self.responses = responses or []


class Parameter:
    def __init__(self, name, location, description=None):
        self.name = name
        self.location = location
        self.description = description


class RequestBody:
    def __init__(self, description=None, content=None):
        self.description = description
        self.content = content  # dictionary of media types and schema


class Response:
    def __init__(self, status_code, description=None, content=None):
        self.status_code = status_code
        self.description = description
        self.content = content  # dictionary of media types and schema



def fetch_specification(source):
    if os.path.isfile(source):  # source is a file
        with open(source, 'r') as f:
            if source.endswith('.yaml'):
                return yaml.safe_load(f)
            elif source.endswith('.json'):
                return json.load(f)
            else:
                raise ValueError("Invalid file type. Only JSON and YAML are supported.")
    else:  # source is a URL
        response = requests.get(source)
        response.raise_for_status()  # raise an exception if the request failed
        if source.endswith('.yaml'):
            return yaml.safe_load(response.text)
        elif source.endswith('.json'):
            return json.loads(response.text)
        else:
            raise ValueError("Invalid URL type. Only JSON and YAML are supported.")
        

# Parse the specification to create instances of Endpoint, Operation, Parameter, RequestBody, and Response.
def extract_api_elements(api_specification):
    pass



def generate_intents(parsed_api):
    # take the parsed OpenAPI description and use it to generate intent examples
    # this could involve filling in sentence templates with the extracted details
    # return the generated intents

    pass



