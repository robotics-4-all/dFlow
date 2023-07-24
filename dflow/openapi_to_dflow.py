from intent_generator import *
from jinja2 import Environment, FileSystemLoader

def create_name(operationId, ending = None):
   if ending == None:
       return operationId
   else:
       return operationId + '_' + ending
    
def create_service(service_name, verb, host, port, path):
    file_loader = FileSystemLoader('templates') 
    env = Environment(loader=file_loader)
    template = env.get_template('grammar-templates/services.jinja')

    output = template.render(service_name=service_name, verb=verb, host=host, port=port, path=path)
    return output

def create_triggers(intent_name, event_name, triggers):
    file_loader = FileSystemLoader('templates') 
    env = Environment(loader=file_loader)
    template = env.get_template('grammar-templates/triggers.jinja')

    phrases = generate_intent_examples(model,tokenizer,operation.summary)
    intent = {
        "type": "Intent",
        "name": intent_name,  
        "phrases": phrases
    }

    event = {
        "type": "Event",
        "name": event_name,  
        "uri": f"bot/event/{event_name}"
    }
    triggers = [intent,event] 

    output = template.render(triggers=triggers)
    return output


fetchedApi = fetch_specification("https://petstore.swagger.io/v2/swagger.json")
parsed_api = extract_api_elements(fetchedApi)  

for endpoint in parsed_api:
    for operation in endpoint.operations:

        triggers = []  

        service_name = create_name(operation.operationId, "svc")
        intent_name = create_name(operation.operationId)
        event_name = create_name(operation.operationId, "ev")
        verb = operation.type.upper() 
        host = fetchedApi["host"]
        port = fetchedApi.get("port", None)
        path = endpoint.path

        eservice_definition = create_service(service_name, verb, host, port, path)
        triggers = create_triggers(intent_name,event_name,triggers)

        print(eservice_definition)
        print(triggers)


