import os.path
import requests
import yaml
import json
from transformers import AutoModelForCausalLM, AutoTokenizer


class Endpoint:
    def __init__(self, path):
        self.path = path
        self.operations = []  # list of Operation objects


class Operation:
    def __init__(self, type, operationId=None, summary=None, description=None, parameters=None, requestBody=None, responses=None):
        self.type = type
        self.operationId = operationId  # new field
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
                    parameter = Parameter(name, location, description)
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
                    content = response_details.get('content')
                    response = Response(status_code, description, content)
                    responses.append(response)

            operation = Operation(operation_type, operationId, operationSummary, operationdDescription, parameters, requestBody, responses)
            endpoint.operations.append(operation)

        endpoints.append(endpoint)

    return endpoints

def generate_intent_examples(model, tokenizer, operation_summary):
    
    # Build the prompt text
    prompt_text = f"""
    I need diverse examples of how a user might express certain intents related to tasks they want to perform. The examples should be human-like, varied, and cover different ways the same intent might be expressed. Here are a few tasks:

    Task: Get user details
    Example Intents:
    1. Can you fetch the details for this user?
    2. Show me the user's information.
    3. I'd like to see this user's details.

    Task: Create a new user
    Example Intents:
    1. I want to register a new user.
    2. Can we set up a user profile?
    3. Let's create a new user account.

    Task: Find pet
    Example Intents:
    1. Where is my pet?
    2. Find my pet!
    3. I've lost my pet, could you locate it?

    Task: Upload an image
    Example Intents:
    1. I want to upload this picture.
    2. Can you assist me in uploading an image?
    3. Post this image now!

    Now, for the following task, please generate 10 diverse intent examples:

    Task: {operation_summary.lower()}
    Intents: 
    """

    # Encode the prompt text
    inputs = tokenizer.encode(prompt_text, return_tensors="pt")

    # Generate text
    outputs = model.generate(
        inputs,
        max_length=500,
        temperature=0.7,
        do_sample=True,
        num_return_sequences=1,  # Generate one sequence and extract examples from it
        pad_token_id=tokenizer.eos_token_id
    )

    # Decode the output
    decoded_output = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Extract the intent examples
    intent_examples_raw = decoded_output.split("Intents:")[-1].strip()
    intent_examples = intent_examples_raw.split('\n')

    # Clean up the extracted examples and remove any empty examples
    clean_intent_examples = [example.split(')')[-1].strip() for example in intent_examples if example.strip()]

    return clean_intent_examples


# model_name = "tiiuae/falcon-7b-instruct"
# model = AutoModelForCausalLM.from_pretrained(model_name, trust_remote_code=True)    
# tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

# # Sample usage
parsed_api = extract_api_elements(fetch_specification("https://petstore.swagger.io/v2/swagger.json"))  

# for endpoint in parsed_api:
#     for operation in endpoint.operations:
#         print(f"Endpoint: {endpoint.path}   \nOperation: {operation.type}")
#         print(f"Summary: {operation.summary}")
#         print("Intent examples:")
#         examples = generate_intent_examples(model,tokenizer,operation.summary)
#         for i, example in enumerate(examples, 1):
#             print(f"{i}) {example}")
#         print("\n")
