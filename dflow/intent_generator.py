import os.path
import spacy
import requests
import yaml
import json


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



def parse_api(api_specification):
    # use spaCy to parse the API specification
    # extract relevant details

    return 0 #details


def generate_intents(parsed_api):
    # take the parsed OpenAPI description and use it to generate intent examples
    # this could involve filling in sentence templates with the extracted details
    # return the generated intents

    return 0 #intents


