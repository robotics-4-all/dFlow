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

    output = template.render(service_name=service_name, verb=verb, host=host, port=port, path=path)
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



def create_dialogue(dialogue_name, intent_name, service_name, parameters,triggers):
    template = jinja_env.get_template('dialogues.jinja')

    form_slots = []

    entities = []
    for phrase in triggers:
        doc = nlp(phrase)
        for ent in doc.ents:
            if ent.label_ in PRETRAINED_ENTITIES:
                entities.append(ent.label_)

    entity_counts = Counter(entities)
    dominant_entity, _ = entity_counts.most_common(1)[0] if entity_counts else (None, None)
    context = "PE:" + dominant_entity if dominant_entity else None


    for param in parameters:
        if param.required:  
            param_type = change_type_name(param.ptype)
            if param_type is None:  
                dlg_type = "ActionGroup"
                response = {
                    "type": dlg_type,
                    "name": create_name(operation.operationId),
                    "actions": [service_name],
                    "text": "Your request has been processed successfully. Is there anything else I can help you with?"
                }
                dialogue = {
                    "name": dialogue_name,
                    "triggers": [intent_name],
                    "responses": [response]
                }
                output = template.render(dialogues=[dialogue])
                return output 

            prompt_text = f"Please provide the {param.name}"
            doc = nlp(prompt_text)

            slot = {
                "name": param.name,
                "type": param_type,
                "prompt": prompt_text
            }

            if context:  
                slot["context"] = context
            form_slots.append(slot)

    if form_slots:
        dlg_type = "Form"
        response = {
            "type": dlg_type,
            "name": create_name(operation.operationId),
            "slots": form_slots,
            "actions": [service_name], 
            "text": "Is there anything else I can help you with?"
        }
    else:  
        dlg_type = "ActionGroup"
        response = {
            "type": dlg_type,
            "name": create_name(operation.operationId),
            "actions": [service_name],
            "text": "Your request has been processed successfully. Is there anything else I can help you with?"
        }

    dialogue = {
        "name": dialogue_name,
        "triggers": [intent_name],
        "responses": [response]
    }

    output = template.render(dialogues=[dialogue])
    return output

fetchedApi = fetch_specification("/Users/harabalos/Desktop/petstore.json")
parsed_api = extract_api_elements(fetchedApi)

for endpoint in parsed_api:
    for operation in endpoint.operations:

        triggersList = []  

        service_name = create_name(operation.operationId, "svc")
        intent_name = create_name(operation.operationId)
        dialogue_name = create_name(operation.operationId, "dialogue")
        verb = operation.type.upper() 
        host = fetchedApi["host"]
        port = fetchedApi.get("port", None)
        path = endpoint.path

        eservice_definition = create_service(service_name, verb, host, port, path)
        triggers = create_trigger(intent_name)
        triggersList = triggers.split("\n")
        dialogues = create_dialogue(dialogue_name, intent_name, service_name, operation.parameters,triggersList)


        print(eservice_definition)
        print(triggers)
        print(dialogues)