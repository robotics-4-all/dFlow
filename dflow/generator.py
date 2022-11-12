from os import path, mkdir, getcwd, chmod
from textx import generator, metamodel_from_file
import jinja2, argparse, itertools, shutil, re
from itertools import groupby
from operator import itemgetter

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
# model = mm.model_from_file('../examples/weather2.dflow')


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
    synonyms_dictionary = {}
    for synonym in model.synonyms:
        data.synonyms.append({'name': synonym.name, 'words': synonym.words})
        synonyms_dictionary[synonym.name] = synonym.words
        if not len(synonym.words):
            raise Exception(f'No examples given for synonym {synonym.name}')

    # Extract trainable entities
    entities_dictionary = {}
    for entity in model.entities:
        if entity.__class__.__name__ == 'PretrainedEntity':
            pass
        else:
            data.entities.append({'name': entity.name, 'words': entity.words})
            entities_dictionary[entity.name] = entity.words
            if not len(entity.words):
                raise Exception(f'No examples given for entity {entity.name}')

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
        if not len(list(set(values))):
            print(f'WARNING: No example given in Pretrained Entity {key}')

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
                        words = entities_dictionary[name]
                        entities_rasa_format = [f"[{ent}]({name})" for ent in words[0]]
                        text.append(entities_rasa_format)
                    elif phrase.__class__.__name__ == "IntentPhraseSynonym":
                        name = phrase.synonym.name
                        words = synonyms_dictionary[name]
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

    # Validate for at least 2 examples per intent
    for intent in data.intents:
        if len(intent['examples']) < 2:
            raise Exception(f'Only {len(intent["examples"])} given in intent {intent["name"]}! At least 2 are needed!')

    # Validate non duplicate dialogue names
    names = [d.name for d in model.dialogues]
    if len(names) != len(set(names)):
        raise Exception('Duplicate dialogue names given!')

    data_slots = []
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
                actions_slots = []
                actions_user_properties = []
                actions_entities = []
                for action in response.actions:
                    if action.__class__.__name__ == 'SpeakAction':
                        message, entities, slots, user_properties, system_properties = process_text(action.text)
                        actions_slots.extend(slots)
                        actions_user_properties.extend(user_properties)
                        actions_entities.extend(entities)
                        actions.append({
                            'type': action.__class__.__name__,
                            'text': message,
                            'system_properties': system_properties
                        })
                    elif action.__class__.__name__ == 'FireEventAction':
                        msg_message, msg_entities, msg_slots, msg_user_properties, msg_system_properties = process_text(action.msg)
                        uri_message, uri_entities, uri_slots, uri_user_properties, uri_system_properties = process_text(action.uri)
                        actions_slots.extend(msg_slots + uri_slots)
                        actions_user_properties.extend(msg_user_properties+uri_user_properties)
                        actions_entities.extend(msg_entities + uri_entities)
                        actions.append({
                            'type': action.__class__.__name__,
                            'uri': uri_message.replace(' ', ''),
                            'msg': msg_message,
                            'system_properties': msg_system_properties+uri_system_properties
                        })
                    elif action.__class__.__name__ == 'SetSlot':
                        result, slots, user_properties, system_properties = process_parameter_value(action.value)
                        actions_slots.extend(slots)
                        actions_user_properties.extend(user_properties)
                        actions.append({
                            'type': action.__class__.__name__,
                            'slot': action.slotRef.param.name,
                            'value': result,
                            'system_properties': system_properties
                        })
                    elif action.__class__.__name__ == 'EServiceCallHTTP':
                        path_params, path_slots, path_user_properties, path_system_properties = process_eservice_params_as_dict(action.path_params)
                        query_params, query_slots, query_user_properties, query_system_properties = process_eservice_params(action.query_params)
                        header_params, header_slots, header_user_properties, header_system_properties = process_eservice_params(action.header_params)
                        body_params, body_slots, body_user_properties, body_system_properties = process_eservice_params(action.body_params)
                        validation = validate_path_params(data.eservices[action.eserviceRef.name]['url'], path_params)
                        if not validation:
                            raise Exception('Service path and path params do not match.')
                        actions_slots.extend(path_slots + query_slots + header_slots + body_slots)
                        actions_user_properties.extend(path_user_properties+query_user_properties+header_user_properties+body_user_properties)

                        actions.append({
                            'type': action.__class__.__name__,
                            'verb': action.eserviceRef.verb.lower(),
                            'url': data.eservices[action.eserviceRef.name]['url'],
                            'query_params': query_params,
                            'path_params': path_params,
                            'header_params': header_params,
                            'body_params': body_params,
                            'response_filter': action.response_filter,
                            'system_properties': list(set(path_system_properties+query_system_properties+header_system_properties+body_system_properties))
                        })
                # Validate action before appending it to data object
                validation = True
                for action_group in data.actions:
                    if action_group['name'] == f"action_{response.name}":
                        if action_group['actions'] == actions:
                            print(f'WARNING: Action Group {action_group["name"]} defined twice...')
                            validation = False
                        else:
                            raise Exception(f'Action Group {action_group["name"]} defined twice with different actions!')
                # Merge slots/entities etc before appending
                if validation:
                    actions_slots = list(set(actions_slots))
                    actions_user_properties = list(set(actions_user_properties))
                    actions_entities = list(set(actions_entities))
                    data.actions.append({
                        "name": f"action_{response.name}",
                        "actions": actions,
                        "slots": actions_slots,
                        "user_properties": actions_user_properties,
                        "entities": actions_entities
                    })
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
                    if slot.source.__class__.__name__ == 'EServiceCallHTTP':
                        path_params, path_slots, path_user_properties, path_system_properties = process_eservice_params_as_dict(slot.source.path_params)
                        query_params, query_slots, query_user_properties, query_system_properties = process_eservice_params(slot.source.query_params)
                        header_params, header_slots, header_user_properties, header_system_properties = process_eservice_params(slot.source.header_params)
                        body_params, body_slots, body_user_properties, body_system_properties = process_eservice_params(slot.source.body_params)
                        validation = validate_path_params(data.eservices[slot.source.eserviceRef.name]['url'], path_params)
                        if not validation:
                            raise Exception('Service path and path params do not match.')
                        slot_service_info = {
                            'type': slot.source.__class__.__name__,
                            'verb': slot.source.eserviceRef.verb.lower(),
                            'url': data.eservices[slot.source.eserviceRef.name]['url'],
                            'query_params': query_params,
                            'path_params': path_params,
                            'header_params': header_params,
                            'body_params': body_params,
                            'response_filter': process_response_filter(slot.source.response_filter),
                            'slots': list(set(path_slots + query_slots + header_slots + body_slots)),
                            'user_properties': list(set(path_user_properties+query_user_properties+header_user_properties+body_user_properties)),
                            'system_properties': list(set(path_system_properties+query_system_properties+header_system_properties+body_system_properties))
                        }
                        validation_data.append({
                            'form': form,
                            'name': slot.name,
                            'method': f'extract_{slot.name}',
                            'type': slot.type,
                            'source_type': slot.source.__class__.__name__,
                            'data': slot_service_info
                        })
                        extract_slot.append({'type': 'custom', 'form': form})
                    elif slot.source.__class__.__name__ == 'HRIParamSource':
                        # No method given, extract from text
                        if slot.source.extract == []:
                            extract_slot.append({'type': 'from_text', 'form': form})
                            extract_from_text = True
                        else:
                            slot_from_intent_info = []
                            for extract_method in slot.source.extract:
                                if extract_method.__class__.__name__ == 'ExtractFromIntent':
                                    value, slots, user_properties, system_properties = process_parameter_value(extract_method.value)
                                    slot_from_intent_info.append({
                                        'type': 'from_intent',
                                        'form': form,
                                        'intent': extract_method.intent.name,
                                        'value': value,
                                        'slots': slots,
                                        'user_properties': user_properties,
                                        'system_properties': system_properties
                                    })
                                elif extract_method.__class__.__name__ == 'TrainableEntityRef':
                                    extract_slot.append({'type': 'from_entity', 'form': form, 'entity': extract_method.entity.name})
                                elif extract_method.__class__.__name__ == 'PretrainedEntityRef':
                                    extract_slot.append({'type': 'from_entity', 'form': form, 'entity': extract_method.entity})
                            # Merge all from_intent information and pass them (if they exist) to validation_data list
                            # so that the correct value will be assigned inside Rasa action server
                            if slot_from_intent_info != []:
                                extract_slot.append({'type': 'custom', 'form': form})
                                validation_data.append({
                                    'form': form,
                                    'name': slot.name,
                                    'method': f'extract_{slot.name}',
                                    'type': slot.type,
                                    'source_type': slot.source.__class__.__name__,
                                    'source_method': 'from_intent',
                                    'data': slot_from_intent_info
                                })
                        if extract_from_text and slot.type in ['int', 'float']:
                            validation_data.append({
                                'form': form,
                                'name': slot.name,
                                'method': f'extract_{slot.name}',
                                'source_type': slot.source.__class__.__name__,
                                'type': slot.type
                            })
                        message, entities, slots, user_properties, system_properties = process_text(slot.source.askSlot)
                        data.actions.append({
                            'name': f"action_ask_{form}_{slot.name}",
                            'entities': entities,
                            'slots': slots,
                            'user_properties': user_properties,
                            'actions': [{
                                'type': 'AskSlot',
                                'text': message,
                                'system_properties': system_properties
                            }]
                        })
                    data_slots.append({'name': slot.name, 'type': slot.type, 'extract_methods': extract_slot})
                data.forms.append({'name': form, 'slots': form_data})
                if validation_data != []:
                    data.actions.append({'name': f'validate_{form}', 'validation_method': True, 'info': validation_data})
        for intent in intents:
            data.stories.append({
                'name': f"{name} - {intent.name}",
                'intent': intent.name,
                'responses': dialogue_responses
            })

    # Validate and merge slots with similar name for the domain file
    data_slots = sorted(data_slots, key = itemgetter('name'))
    for k, v in groupby(data_slots, key = itemgetter('name')):
        slots = list(v)
        types = [slot['type'] for slot in slots]
        type = types[0]
        # Check same named slots to have the same type
        if len(set(types)) > 1:
            raise Exception(f"Error! More than one slot types given to slot named {k}. Please set the same type or modify the slot names!")
        # Merge them into one dict
        extract_methods = []
        for slot in slots:
            for method in slot['extract_methods']:
                if method not in extract_methods:
                    extract_methods.append(method)
        data.slots.append({'name': k, 'type': type, 'extract_methods': extract_methods})

    return data

def process_text(text):
    """ Takes a Text entity, processes the entities, slots, and user properties and converts them to string."""
    if isinstance(text, str):
        return text, [], [], [], []
    message = []
    entities = []
    slots = []
    user_properties = []
    system_properties = []
    for phrase in text:
        if phrase.__class__.__name__ == 'TextEntity':
            message.extend(["{", f"{phrase.entity.name}", "}"])
            entities.append(phrase.entity.name)
        elif phrase.__class__.__name__ == 'FormParamRef':
            slots.append(phrase.param.name)
            message.extend(["{", f"{phrase.param.name}", "}"])
        elif phrase.__class__.__name__ == 'UserPropertyDef':
            message.extend(["{", f"{phrase.property}", "}"])
            user_properties.append(phrase.property)
        elif phrase.__class__.__name__ == 'SystemPropertyDef':
            message.extend(["{", f"{phrase.property}", "}"])
            system_properties.append(phrase.property)
        else:
            message.append(phrase)
    return ' '.join(message), entities, slots, user_properties, system_properties

def process_parameter_value(param):
    """
        Takes a ParameterValue entity and recursively creates a tempale-ready string
        to send to the templates.
        It also returns all needed slots, user and system properties.
    """
    slots = []
    user_properties = []
    system_properties = []
    if param == []:
        param = ''
    elif isinstance(param, (int, str, bool, float)):
        result = f"\"{param}\""
        return result, [], [], []
    elif param.__class__.__name__ == 'Dict':
        result = '{'
        for item in param.items:
            item_results, item_slots, item_user_properties, item_system_properties = process_parameter_value(item.value)
            slots.extend(item_slots)
            user_properties.extend(item_user_properties)
            system_properties.extend(item_system_properties)
            result = result + f"'{item.name}': {item_results}, "
        result = result + '}'
    elif param.__class__.__name__ == 'List':
        result = '['
        for item in param.items:
            item_results, item_slots, item_user_properties, item_system_properties = process_parameter_value(item)
            slots.extend(item_slots)
            user_properties.extend(item_user_properties)
            system_properties.extend(item_system_properties)
            result = result + item_results
        result = result + ']'
    elif param.__class__.__name__ == 'FormParamRef':
        new_slot = ['f"{', f"{param.param.name}", '}"']
        result = ''.join(new_slot)
        slots.append(f"{param.param.name}")
    elif param.__class__.__name__ == 'UserPropertyDef':
        new_slot = ['f"{', f"{param.property}", '}"']
        result = ''.join(new_slot)
        user_properties.append(param.property)
    elif param.__class__.__name__ == 'SystemPropertyDef':
        new_slot = ['f"{', f"{param.property}", '}"']
        result = ''.join(new_slot)
        system_properties.append(param.property)
    return result, slots, user_properties, system_properties

def process_eservice_params(params):
    """
        Takes an EServiceParam entity (name, value) and recursively creates a dictionary
        with the names as keys and the value as values for each one in a f-string format.
        It also returns all needed slots, user and system properties.
        That way all needed slots and properties can be included inside the f-strings of the values.
    """
    results = '{'
    slots = []
    user_properties = []
    system_properties = []
    if params.__class__.__name__ != 'list':
        return process_parameter_value(params)
    for param in params:
        results = results + f"\"{param.name}\": "
        if param.value.__class__.__name__ == 'Dict':
            dict_results = '{'
            for item in param.value.items:
                item_results, item_slots, item_user_properties, item_system_properties = process_eservice_params(item.value)
                slots.extend(item_slots)
                user_properties.extend(item_user_properties)
                system_properties.extend(item_system_properties)
                dict_results = dict_results + f"'{item.name}': {item_results}, "
            dict_results = dict_results + '}'
            results = results + f"{dict_results}, "
        elif param.value.__class__.__name__ == 'List':
            list_results = '['
            list_length = len(param.value.items)
            for i in range(len(param.value.items)):
                item = param.value.items[i]
                item_results, item_slots, item_user_properties, item_system_properties = process_eservice_params(item)
                slots.extend(item_slots)
                user_properties.extend(item_user_properties)
                system_properties.extend(item_system_properties)
                list_results = list_results + item_results
                if i < list_length - 1:
                    list_results = list_results + ', '
            list_results = list_results + ']'
            results = results + f"{list_results}, "
        else:
            param_result, param_slots, param_user_properties, param_system_properties = process_parameter_value(param.value)
            slots.extend(param_slots)
            user_properties.extend(param_user_properties)
            system_properties.extend(param_system_properties)
            results = results + param_result + ', '
    results = results + '}'
    return results, list(set(slots)), list(set(user_properties)), list(set(system_properties))

def process_eservice_params_as_dict(params):
    """
        Takes an EServiceParam entity (name, value) and recursively creates a dictionary
        with the names as keys and the value as values for each one.
        It also returns all needed slots, user and system properties.
    """
    results = {}
    slots = []
    user_properties = []
    system_properties = []
    if params == []:
        return {}, [], [], []
    if isinstance(params, (int, str, bool, float)):
        return params, [], [], []
    if params.__class__.__name__ == 'FormParamRef':
        new_slot = ["{", f"{params.param.name}", "}"]
        slots.append(f"{params.param.name}")
        return ' '.join(new_slot), slots, user_properties, system_properties
    elif params.__class__.__name__ == 'UserPropertyDef':
        new_slot = ["{", f"{params.name}", "}"]
        user_properties.append(params.name)
        return ' '.join(new_slot), slots, user_properties, system_properties
    elif params.__class__.__name__ == 'SystemPropertyDef':
        new_slot = ["{", f"{params.name}", "}"]
        system_properties.append(params.name)
        return ' '.join(new_slot), slots, user_properties, system_properties
    for param in params:
        if param.value.__class__.__name__ == 'Dict':
            dict_results = {}
            for item in param.value.items:
                item_results, item_slots, item_user_properties, item_system_properties = process_eservice_params(item.value)
                slots.extend(item_slots)
                user_properties.extend(item_user_properties)
                system_properties.extend(item_system_properties)
                dict_results[item.name] = item_results
            results[param.name] = dict_results
        elif param.value.__class__.__name__ == 'List':
            list_results = []
            for item in param.value.items:
                item_results, item_slots, item_user_properties, item_system_properties = process_eservice_params(item)
                slots.extend(item_slots)
                user_properties.extend(item_user_properties)
                system_properties.extend(item_system_properties)
                if isinstance(item_results, (int, str, bool, float)):
                    item_results = [item_results]
                list_results.extend(item_results)
            results[param.name] = list_results
        elif param.value.__class__.__name__ == 'FormParamRef':
            new_slot = ["{", f"{param.value.param.name}", "}"]
            results[param.name] = ' '.join(new_slot)
            slots.append(f"{param.value.param.name}")
        elif param.value.__class__.__name__ == 'UserPropertyDef':
            new_slot = ["{", f"{param.name}", "}"]
            user_properties.append(param.name)
            results[param.name] = ' '.join(new_slot)
        elif param.value.__class__.__name__ == 'SystemPropertyDef':
            new_slot = ["{", f"{param.name}", "}"]
            system_properties.append(param.name)
            results[param.name] = ' '.join(new_slot)
        else:
            results[param.name] = param.value
    return results, list(set(slots)), list(set(user_properties)), list(set(system_properties))

def process_response_filter(text):
    """ Convert response filtering to template-ready string. """
    if text is None:
        return ''
    return ''.join([f"[{word}]" if word.isnumeric() else f"[\'{word}\']" for word in text.split('.')])

def validate_path_params(url, path_params):
    ''' Check whether all path_params keys and params in url match. '''
    return True
    url_params = re.findall("{[a-z|A-Z]+}", url)
    url_params = [url[1:-1] for url in url_params]  # Discard brackets
    return url_params == list(path_params.keys())
