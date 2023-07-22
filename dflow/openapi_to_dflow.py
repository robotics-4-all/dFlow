from intent_generator import *
from jinja2 import Environment, FileSystemLoader

def create_service_name(operationId):
   return f'{operationId}_svc'
    
def create_intent_name(operationId):
    return f'{operationId}'

def create_service(service_name, verb, host, port, path):
    file_loader = FileSystemLoader('templates') 
    env = Environment(loader=file_loader)
    template = env.get_template('grammar-templates/services.jinja')

    output = template.render(service_name=service_name, verb=verb, host=host, port=port, path=path)
    return output

def create_intents(name, triggers):
    file_loader = FileSystemLoader('templates') 
    env = Environment(loader=file_loader)
    template = env.get_template('grammar-templates/triggers.jinja')

    phrases = generate_intent_examples(model,tokenizer,operation.summary)
    trigger = {
        "type": "Intent",
        "name": name,  
        "phrases": phrases
    }
    triggers = [trigger] 

    output = template.render(triggers=triggers)
    return output


fetchedApi = fetch_specification("https://petstore.swagger.io/v2/swagger.json")
parsed_api = extract_api_elements(fetchedApi)  

for endpoint in parsed_api:
    for operation in endpoint.operations:

        triggers = []  
        service_name = create_service_name(operation.operationId)
        intent_name = create_intent_name(operation.operationId)
        verb = operation.type.upper() 
        host = fetchedApi["host"]
        port = fetchedApi.get("port", None)
        path = endpoint.path

        eservice_definition = create_service(service_name, verb, host, port, path)
        intents = create_intents(intent_name,triggers)

        print(eservice_definition)
        print(intents)

