from intent_generator import Endpoint, Operation, Parameter,RequestBody,Response,fetch_specification, extract_api_elements,generate_intent_examples
from jinja2 import Environment, FileSystemLoader

def create_service_name(operationId):
    service_name = f'{operationId}_svc'
    return service_name

def create_service(service_name, verb, host, port, path):
    file_loader = FileSystemLoader('templates') 
    env = Environment(loader=file_loader)
    template = env.get_template('grammar-templates/services.jinja')

    output = template.render(service_name=service_name, verb=verb, host=host, port=port, path=path)
    return output

# def create_intents(triggers):
#     file_loader = FileSystemLoader('templates') 
#     env = Environment(loader=file_loader)
#     template = env.get_template('grammar-templates/triggers.jinja')

#     phrases = generate_intent_examples(model, tokenizer, operation_summary)
#     trigger = {
#         "type": "Intent",
#         "name": "generated_intent_name", 
#         "phrases": phrases
#     }
#     triggers = [trigger]  

#     output = env.from_string('{% extends "dflow.jinja" %}{% block triggers %}' + template.blocks['triggers'][0]() + '{% endblock %}').render(triggers=triggers)
#     return output


fetchedApi = fetch_specification("https://petstore.swagger.io/v2/swagger.json")
parsed_api = extract_api_elements(fetchedApi)  

for endpoint in parsed_api:
    for operation in endpoint.operations:
        service_name = create_service_name(operation.operationId)
        verb = operation.type.upper() 
        host = fetchedApi["host"]
        port = fetchedApi.get("port", None)
        path = endpoint.path

        eservice_definition = create_service(service_name, verb, host, port, path)

        print(eservice_definition)

