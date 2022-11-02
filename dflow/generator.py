from os import path, mkdir, getcwd, chmod
from textx import generator, metamodel_from_file
import jinja2, argparse, itertools, shutil, re

from textxjinja import textx_jinja_generator
import textx.scoping.providers as scoping_providers
from rich import print
from pydantic import BaseModel
from typing import Any, List, Dict

_THIS_DIR = path.realpath(getcwd())

# Initialize template engine.
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(path.join(_THIS_DIR, 'templates')),
    trim_blocks=True,
    lstrip_blocks=True)

srcgen_folder = path.join(path.realpath(getcwd()), 'gen')


# mm = metamodel_from_file('dflow.tx')
# mm.register_scope_providers(
#         {
#             "*.*": scoping_providers.FQN()
#         }
#     )
# model = mm.model_from_file('../examples/simple.dflow')


class TransformationDataModel(BaseModel):
    synonyms: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []
    pretrained_entities: List[Dict[str, Any]] = []
    intents: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    eservices: Dict[str, Any] = {}
    stories: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    rules: List[Dict[str, Any]] = []
    slots: List[Dict[str, Any]] = []
    forms: List[Dict[str, Any]] = []
    responses: List[Dict[str, Any]] = []

@generator('dflow', 'rasa')
def dflow_generate_rasa(metamodel, model, output_path, overwrite,
        debug, **custom_args):
    "Generator for generating rasa from dflow descriptions"
    data = parse_model(model)

    # Prepare generating file directory
    if output_path is None:
        out_dir = srcgen_folder
    else:
        out_dir = output_path

    if not path.exists(out_dir):
        mkdir(out_dir)

    if not path.exists(path.join(out_dir, 'actions')):
        mkdir(path.join(out_dir, 'actions'))

    if not path.exists(path.join(out_dir, 'data')):
        mkdir(path.join(out_dir, 'data'))

    if not path.exists(path.join(out_dir, 'models')):
        mkdir(path.join(out_dir, 'models'))

    # Generate
    templates = [
        'actions/actions.py.jinja', 'data/nlu.yml.jinja',
        'data/stories.yml.jinja', 'data/rules.yml.jinja',
        'config.yml.jinja', 'domain.yml.jinja'
        ]
    static_templates = ['credentials.yml', 'endpoints.yml']

    for file in templates:
        gen_file_name = path.splitext(file)[0]

        out_file = path.join(out_dir, gen_file_name)
        template = jinja_env.get_template(file)
        with open(path.join(out_file), 'w') as f:
            f.write(template.render(intents=data.intents,
                                    synonyms=data.synonyms,
                                    pretrained_entities=data.pretrained_entities,
                                    entities=data.entities,
                                    events=data.events,
                                    eservices=data.eservices,
                                    stories=data.stories,
                                    actions=data.actions,
                                    rules=data.rules,
                                    slots=data.slots,
                                    forms=data.forms,
                                    responses=data.responses))
        chmod(out_file, 509)

    for file in static_templates:
        out_file = path.join(out_dir, file)
        template = path.join(path.join(_THIS_DIR, 'templates', file))
        shutil.copyfile(template, out_file)
        chmod(out_file, 509)

    return out_dir

def parse_model(model) -> TransformationDataModel:
    data = TransformationDataModel()
    # Extract synonyms
    for synonym in model.synonyms:
        data.synonyms.append({'name': synonym.name, 'words': synonym.words})

    # Extract trainable entities
    for entity in model.entities:
        if entity.__class__.__name__ == 'PretrainedEntity':
            pass
        else:
            data.entities.append({'name': entity.name, 'words': entity.words})

    # Extract pretrained entities with examples
    pretrained_entities_examples = {}
    for trigger in model.triggers:
        if trigger.__class__.__name__ == 'Intent':
            for complex_phrase in trigger.phrases:
                for phrase in complex_phrase.phrases:
                    if phrase.__class__.__name__ == "IntentPhrasePE":
                        name = phrase.pretrained
                        if name not in data.pretrained_entities:
                            data.pretrained_entities.append(name)
                        if name not in pretrained_entities_examples:
                            pretrained_entities_examples[name] = []
                        if phrase.refPreValues != []:
                            pretrained_entities_examples[name].extend(phrase.refPreValues)

    for key, values in pretrained_entities_examples.items():
        pretrained_entities_examples[key] = list(set(values))

    # Extract external services
    for service in model.eservices:
        service_info = {}
        service_info['verb'] = service.verb
        service_info['host'] = service.host
        if service.port:
            service_info['port'] = service.port
            port = f":{service.port}"
        else:
            service_info['port'] = ''
            port = ''
        service_info['path'] = service.path
        service_info['url'] = f"{service_info['host']}{port}{service_info['path']}"
        data.eservices[service.name] = service_info

    # Extract triggers
    for trigger in model.triggers:
        if trigger.__class__.__name__ == 'Intent':
            examples = []
            for complex_phrase in trigger.phrases:
                text = []
                for phrase in complex_phrase.phrases:
                    if phrase.__class__.__name__ == 'str':
                        text.append([phrase])
                    elif phrase.__class__.__name__ == "IntentPhraseTE":
                        name = phrase.trainable.name
                        words = [entity["words"] for entity in data.entities if entity['name'] == name]
                        entities_rasa_format = [f"[{ent}]({name})" for ent in words[0]]
                        text.append(entities_rasa_format)
                    elif phrase.__class__.__name__ == "IntentPhraseSynonym":
                        name = phrase.synonym.name
                        words = [synonym["words"] for synonym in data.synonyms if synonym['name'] == name]
                        synonym = words[0][0]
                        text.append([synonym])
                    elif phrase.__class__.__name__ == "IntentPhrasePE":
                        name = phrase.pretrained
                        if pretrained_entities_examples[name] != []:
                            text.append(pretrained_entities_examples[name])
                example = [' '.join(sentence) for sentence in itertools.product(*text)]
                examples.extend(example)
            data.intents.append({'name': trigger.name, 'examples': list(set(examples))})
        else:
            data.events.append({'name': trigger.name, 'uri': trigger.uri})

    # Extract dialogues
    for dialogue in model.dialogues:
        name = dialogue.name
        intents = dialogue.onTrigger
        dialogue_responses = []
        for i in range(len(dialogue.responses)) :
            response = dialogue.responses[i]
            if response.__class__.__name__ == 'ActionGroup':
                dialogue_responses.append({"name": f"action_{response.name}", "form": False})
                actions = []
                for action in response.actions:
                    if action.__class__.__name__ == 'SpeakAction':
                        message, entities, slots = process_text(action.text)
                        actions.append({
                            'type': action.__class__.__name__,
                            'text': message,
                            'entities': entities,
                            'slots': slots
                        })
                    elif action.__class__.__name__ == 'FireEventAction':
                        message, entities, slots = process_text(action.msg)
                        actions.append({
                            'type': action.__class__.__name__,
                            'uri': action.uri,
                            'msg': message,
                            'entities': entities,
                            'slots': slots
                        })
                    elif action.__class__.__name__ == 'SetSlot':
                        actions.append({
                            'type': action.__class__.__name__,
                            'slot': action.slotRef.param.name,
                            'value': action.value
                        })
                    elif action.__class__.__name__ == 'EServiceCallHTTP':
                        path_params, path_slots = process_http_params(action.path_params)
                        query_params, query_slots = process_http_params(action.query_params)
                        header_params, header_slots = process_http_params(action.header_params)
                        body_params, body_slots = process_http_params(action.body_params)
                        validation = validate_path_params(data.eservices[action.eserviceRef.name]['url'], path_params)
                        if not validation:
                            raise Exception('Service path and path params do not match.')
                        actions.append({
                            'type': action.__class__.__name__,
                            'verb': action.eserviceRef.verb.lower(),
                            'url': data.eservices[action.eserviceRef.name]['url'],
                            'query_params': query_params,
                            'path_params': path_params,
                            'header_params': header_params,
                            'body_params': body_params,
                            'response_filter': action.response_filter,
                            'slots': list(set(path_slots + query_slots + header_slots + body_slots))
                        })
                data.actions.append({"name": f"action_{response.name}", "actions": actions})
            elif response.__class__.__name__ == 'Form':
                form = f"{response.name}_form"
                dialogue_responses.append({"name": form, "form": True})
                for intent in intents:
                    data.rules.append({
                        'name': f"Activate {form} with {intent.name}",
                        'form': form,
                        'intent': intent.name,
                        'responses': dialogue_responses.copy(),
                        'type': 'Activate'
                    })
                if i < len(dialogue.responses) - 1:
                    next_actions = [{"name": f"action_{action.name}", "form": False} for action in dialogue.responses[i+1:]]
                else:
                    next_actions = []

                data.rules.append({
                    'name': f"Submit {form}",
                    'form': form,
                    'responses': next_actions,
                    'type': 'Submit'
                })

                form_data = []
                validation_data = []
                for slot in response.params:
                    extract_slot = []
                    extract_from_text = False
                    form_data.append(slot.name)
                    for extract_method in slot.extract:
                        if extract_method.__class__.__name__ == 'str':
                            extract_slot.append({'type': extract_method.__class__.__name__})    # extract_method == 'text'
                            extract_from_text = True
                        elif extract_method.__class__.__name__ == 'FromIntent':
                            extract_slot.append({
                                'type': extract_method.__class__.__name__,
                                'intent': extract_method.intent.name,
                                'value': extract_method.value
                            })
                        elif extract_method.__class__.__name__ == 'FromEntity':
                            extract_slot.append({'type': extract_method.__class__.__name__, 'entity': extract_method.entity.name})
                    if extract_from_text and slot.type in ['int', 'float']:
                        validation_data.append({
                            'form': form,
                            'name': slot.name,
                            'method': f'extract_{slot.name}',
                            'type': slot.type
                        }) # extract_method == 'text
                    data.slots.append({'name': slot.name, 'form': form, 'type': slot.type, 'extract_methods': extract_slot})
                    data.responses.append({
                        'name': f"utter_ask_{form}_{slot.name}",
                        'text': slot.source.ask_slot
                    })
                data.forms.append({'name': form, 'slots': form_data})
                if validation_data != []:
                    data.actions.append({'name': f'validate_{form}', 'validation_method': True, 'info': validation_data})
        for intent in intents:
            data.stories.append({
                'name': f"{name} - {intent.name}",
                'intent': intent.name,
                'responses': dialogue_responses
            })
    return data

def process_text(text):
    if isinstance(text, str):
        return text, []
    message = []
    entities = []
    slots = []
    for phrase in text:
        if phrase.__class__.__name__ == 'TextEntity':
            message.extend(["{", f"{phrase.entity.name}", "}"])
            entities.append(phrase.entity.name)
        elif phrase.__class__.__name__ == 'FormParamRef':
            slots.append(phrase.param.name)
            message.extend(["{", f"{phrase.param.name}", "}"])
        else:
            message.append(phrase)
    return ' '.join(message), entities, slots

def process_http_params(params):
    results = {}
    slots = []
    if isinstance(params, (int, str, bool, float)):
        return params, []
    for param in params:
        if param.value.__class__.__name__ == 'Dict':
            dict_results = {}
            for item in param.value.items:
                item_results, item_slots = process_http_params(item.value)
                slots.extend(item_slots)
                dict_results[item.name] = item_results
            results[param.name] = dict_results
        elif param.value.__class__.__name__ == 'List':
            list_results = []
            for item in param.value.items:
                item_results, item_slots = process_http_params(item)
                slots.extend(item_slots)
                if isinstance(item_results, (int, str, bool, float)):
                    item_results = [item_results]
                list_results.extend(item_results)
            results[param.name] = list_results
        elif param.value.__class__.__name__ == 'FormParamRef':
            new_slot = ["{", f"{param.value.param.name}", "}"]
            results[param.name] = ' '.join(new_slot)
            slots.append(f"{param.value.param.name}")
        else:
            results[param.name] = param.value
    return results, list(set(slots))

def validate_path_params(url, path_params):
    ''' Check wether all path_params keys and params in url match. '''
    url_params = re.findall("{[a-z|A-Z]+}", url)
    return url_params == list(path_params.keys())
