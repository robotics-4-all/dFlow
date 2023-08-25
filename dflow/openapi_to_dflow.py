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

    if verb == "GET":
        if response_properties and current_path in response_properties:
            if parameters:
                query_parameters = ', '.join([f"{param.name}={form_response['name']}.{param.name}" for param in parameters])
                service_call = f"{service_name}(query=[{query_parameters}],)"
            else:
                service_call = f"{service_name}()"
                
            has_required_response = False

            for prop, prop_data in response_properties[current_path].items():
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
                action_group_response = {
                    "type": "ActionGroup",
                    "name": create_name(dialogue_name, "ag"),
                    "service_call": service_call,
                    "text": "Your request has been processed successfully."
                }
                responses.append(action_group_response)
            else:
                ag_text = "The information you requested is: " + ' '.join([f"{form_response['name']}.{slot['name']}" for slot in form_slots])
                action_group_response = {
                    "type": "ActionGroup",
                    "name": create_name(dialogue_name, "ag"),
                    "text": ag_text
                }
                responses.append(action_group_response)
        else:
            if parameters:
                query_parameters = ', '.join([f"{param.name}={form_response['name']}.{param.name}" for param in parameters])
                service_call = f"{service_name}(query=[{query_parameters}],)"
            else:
                service_call = f"{service_name}()"
                
            action_group_response = {
                "type": "ActionGroup",
                "name": create_name(dialogue_name, "ag"),
                "service_call": service_call,
                "text": "Your request has been processed successfully."
            }
            responses.append(action_group_response)
    elif verb in ["POST", "PUT", "DELETE"]:
        if parameters:
            path_parameters = ', '.join([f"{param.name}={form_response['name']}.{param.name}" for param in parameters if change_type_name(param.ptype) != None and param.required])
            service_call = f"{service_name}(path=[{path_parameters}],)"
        else:
            service_call = f"{service_name}()"
            
        action_group_response = {
            "type": "ActionGroup",
            "name": create_name(dialogue_name, "ag"),
            "service_call": service_call,
            "text": "Your request has been processed successfully."
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