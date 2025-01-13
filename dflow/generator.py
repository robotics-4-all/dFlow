from os import path, mkdir, chmod, getcwd
from textx import generator, metamodel_from_file
import jinja2, argparse, itertools, shutil, re
from itertools import groupby
from operator import itemgetter

import textx.scoping.providers as scoping_providers
from rich import print
from pydantic import BaseModel
from typing import Any, List, Dict, Set

from dflow.utils import get_mm, build_model

import json, os

ALL_ACTIONS = 'all_actions'

_THIS_DIR = path.abspath(path.dirname(__file__))

# Initialize template engine.
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(path.join(_THIS_DIR, 'templates')),
    trim_blocks=True,
    lstrip_blocks=True)

SRC_GEN_DIR = path.join(path.realpath(getcwd()), 'gen')

# Load dynamic templates
TEMPLATES = [
    'actions/actions.py.jinja', 'data/nlu.yml.jinja',
    'data/stories.yml.jinja', 'data/rules.yml.jinja',
    'config.yml.jinja', 'domain.yml.jinja',
    'credentials.yml.jinja'
]

# Load static templates
STATIC_TEMPLATES = [
    'endpoints.yml'
]


class AccessControlMisc():
    policy_path: str = ''
    default_role: str = ''
    role_users: Dict[str, List] = {}
    authentication: Dict[str, Any] = {}
    global_ac: bool = False # True if global(actionGroup) access control is defined
    local_ac: bool = False # True if local(action) access control is defined


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
    connectors: List[Dict[str, Any]] = []
    responses: List[Dict[str, Any]] = []
    roles: List[str] = []
    policies: Dict[str, set] = {}
    ac_misc: AccessControlMisc = AccessControlMisc()
    nlu_config: Dict[str, str] = {}

    class Config:
            arbitrary_types_allowed = True

def codegen(model_fillepath,
            output_path=None,
            overwrite=False,
            debug=True,
             **custom_args):
    metamodel = get_mm()
    model, _ = build_model(model_fillepath)
    return generate(metamodel, model, output_path,
                    overwrite, debug, **custom_args)


@generator('dflow', 'rasa')
def dflow_generate_rasa(metamodel,
                        model,
                        output_path,
                        overwrite,
                        debug,
                        **custom_args) -> None:
    generate(metamodel, model, output_path, overwrite, debug, **custom_args)


def generate(metamodel,
             model,
             output_path,
             overwrite,
             debug,
             **custom_args) -> None:

    # Prepare generating file directory
    if output_path is None:
        out_dir = SRC_GEN_DIR
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

    data = parse_model(model, out_dir)

    # Generate
    for file in TEMPLATES:
        gen_file_name = path.splitext(file)[0]

        out_file = path.join(out_dir, gen_file_name)
        template = jinja_env.get_template(file)
        with open(path.join(out_file), 'w') as f:
            f.write(template.render(
                intents=data.intents,
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
                responses=data.responses,
                connectors=data.connectors,
                roles=data.roles,
                policies=data.policies,
                ac_misc=data.ac_misc,
                nlu_config=data.nlu_config
            )
        )
        chmod(out_file, 509)

    for file in STATIC_TEMPLATES:
        out_file = path.join(out_dir, file)
        template = path.join(path.join(_THIS_DIR, 'templates', file))
        shutil.copyfile(template, out_file)
        chmod(out_file, 509)

    return out_dir


def add_static_scenario(data: TransformationDataModel) -> TransformationDataModel:
    """ Adds a vanilla bot challenge scenario (intent and dialogue) to a provided model. """

    # Add intent with examples
    _intent_name = 'bot_challenge'
    _examples = [
        'who are you?',
        'what are you',
        'are you human or bot',
        'are you a bot',
        'tell me your name',
        'tell me about yourself',
        'what exactly are you',
        'what about you',
        'what\'s your name'
    ]
    data.intents.append({'name': _intent_name, 'examples': _examples})

    # Add action with message
    _message = "I am a bot developed by dFlow and Rasa."
    _actions = []
    _actions.append({
                        'type': 'SpeakAction',
                        'text': _message,
                        'system_properties': [],
                        'roles': []
                    })
    data.actions.append({
                        "name": f"action_{_intent_name}",
                        "actions": _actions,
                        "slots": [],
                        "user_properties": [],
                        "entities": [],
                        "local_ac": False
                        })
    
    # Add dialogue
    dialogue_responses = []
    dialogue_responses.append({"name": f"action_{_intent_name}", "form": False})
    
    data.stories.append({
        'name': f"system_dialogue - {_intent_name}",
        'intent': _intent_name,
        'responses': dialogue_responses
    })
    
    return data

def parse_model(model, out_dir) -> TransformationDataModel:
    data = TransformationDataModel()
    
    data = add_static_scenario(data)

    # Extract nlu_config
    if model.nlu_config:
        data.nlu_config = {'name': model.nlu_config.name, 'weights': model.nlu_config.weights}

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
                    if phrase.__class__.__name__ == "PretrainedEntityRef":
                        name = phrase.entity
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
        
        service_info['mime'] = ''
        if service.mime:
            if service.verb.lower() == 'get':
                for mime in service.mime:
                    service_info['mime'] += f"'Accept': '{mime}', "
            else:
                for mime in service.mime:
                    service_info['mime'] += f"'Content-Type': '{mime}', "
            
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
                    elif phrase.__class__.__name__ == "TrainableEntityRef":
                        name = phrase.entity.name
                        words = entities_dictionary[name]
                        entities_rasa_format = [f"[{ent}]({name})" for ent in words]
                        text.append(entities_rasa_format)
                    elif phrase.__class__.__name__ == "IntentPhraseSynonym":
                        name = phrase.synonym.name
                        words = synonyms_dictionary[name]
                        synonym = words[0]
                        text.append([f"[{synonym}]({name})"])
                    elif phrase.__class__.__name__ == "PretrainedEntityRef":
                        name = phrase.entity
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

    # Add global slots
    for slot in model.gslots:
        data.slots.append({'name': slot.name, 'type': 'any', 'default': slot.default, 'extract_methods': None})

    # Validate non duplicate dialogue names
    names = [d.name for d in model.dialogues]
    if len(names) != len(set(names)):
        raise Exception('Duplicate dialogue names given!')

    form_slots = [] # Collect slots stated in forms
    # Extract dialogues
    for dialogue in model.dialogues:
        name = dialogue.name
        intents = dialogue.onTrigger
        dialogue_responses = []
        dialogue_form_slots = [] # Contains all dialogue's form slots
        for i in range(len(dialogue.responses)):
            response = dialogue.responses[i]
            if response.__class__.__name__ == 'ActionGroup':
                dialogue_responses.append({"name": f"action_{response.name}", "form": False})
                actions = []
                actions_slots = []
                actions_user_properties = []
                actions_entities = []
                action_local_ac = False
                for action in response.actions:
                    roles = []
                    if action.roles:
                        roles = list(set(action.roles))
                        action_local_ac = True
                        data.ac_misc.local_ac = True # Local access control is defined
                    if action.__class__.__name__ == 'SpeakAction':
                        message, entities, slots, user_properties, system_properties = process_text(action.text)
                        actions_slots.extend(slots)
                        actions_user_properties.extend(user_properties)
                        actions_entities.extend(entities)
                        actions.append({
                            'type': action.__class__.__name__,
                            'text': message,
                            'system_properties': system_properties,
                            'roles': roles
                        })
                    elif action.__class__.__name__ == 'FireEventAction':
                        msg_message, msg_slots, msg_user_properties, msg_system_properties = process_parameter_value(action.msg)
                        uri_message, uri_entities, uri_slots, uri_user_properties, uri_system_properties = process_text(action.uri)
                        actions_slots.extend(msg_slots + uri_slots)
                        actions_user_properties.extend(msg_user_properties+uri_user_properties)
                        actions_entities.extend(uri_entities)
                        actions.append({
                            'type': action.__class__.__name__,
                            'uri': uri_message.replace(' ', ''),
                            'msg': msg_message,
                            'system_properties': msg_system_properties+uri_system_properties,
                            'roles': roles
                        })
                    elif action.__class__.__name__ == 'SetFormSlot':
                        result, slots, user_properties, system_properties = process_parameter_value(action.value)
                        actions_slots.extend(slots)
                        actions_user_properties.extend(user_properties)
                        actions.append({
                            'type': action.__class__.__name__,
                            'slot': action.slotRef.param.name,
                            'value': result,
                            'system_properties': system_properties,
                            'roles': roles
                        })
                    elif action.__class__.__name__ == 'SetGlobalSlot':
                        result, slots, user_properties, system_properties = process_parameter_value(action.value)
                        actions_slots.extend(slots)
                        actions_user_properties.extend(user_properties)
                        actions.append({
                            'type': action.__class__.__name__,
                            'slot': action.slotRef.slot.name,
                            'value': result,
                            'system_properties': system_properties,
                            'roles': roles
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

                        if data.eservices[action.eserviceRef.name]['mime']:
                            header_params = merge_header_mimes(header_params, data.eservices[action.eserviceRef.name]['mime'])
                        
                        actions.append({
                            'type': action.__class__.__name__,
                            'verb': action.eserviceRef.verb.lower(),
                            'url': data.eservices[action.eserviceRef.name]['url'],
                            'query_params': query_params,
                            'path_params': path_params,
                            'header_params': header_params,
                            'body_params': body_params,
                            'response_filter': action.response_filter,
                            'system_properties': list(set(path_system_properties+query_system_properties+header_system_properties+body_system_properties)),
                            'roles': roles
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
                        "entities": actions_entities,
                        "local_ac": action_local_ac
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

                form_data = [] # Contains only this form's slots
                validation_data = []
                for i in range(len(response.params)):
                    slot = response.params[i]
                    extract_slot = []
                    extract_from_text = False
                    form_data.append(slot.name)
                    if slot.source.__class__.__name__ == 'EServiceCallHTTP':
                        path_params, path_slots, path_user_properties, path_system_properties = process_eservice_params_as_dict(slot.source.path_params)
                        query_params, query_slots, query_user_properties, query_system_properties = process_eservice_params(slot.source.query_params)
                        header_params, header_slots, header_user_properties, header_system_properties = process_eservice_params(slot.source.header_params)
                        body_params, body_slots, body_user_properties, body_system_properties = process_eservice_params(slot.source.body_params)
                        validation = validate_path_params(data.eservices[slot.source.eserviceRef.name]['url'], path_params)
                        
                        if data.eservices[slot.source.eserviceRef.name]['mime']:
                            header_params = merge_header_mimes(header_params, data.eservices[slot.source.eserviceRef.name]['mime'])
                        
                        if not validation:
                            raise Exception('Service path and path params do not match.')
                        previous_slot_list = []
                        if i > 0:
                            previous_slot = response.params[i-1].name
                            previous_slot_list.append(previous_slot)
                        else:
                            previous_slot = None
                        slot_service_info = {
                            'type': slot.source.__class__.__name__,
                            'verb': slot.source.eserviceRef.verb.lower(),
                            'url': data.eservices[slot.source.eserviceRef.name]['url'],
                            'query_params': query_params,
                            'path_params': path_params,
                            'header_params': header_params,
                            'body_params': body_params,
                            'response_filter': process_response_filter(slot.source.response_filter),
                            'slots': list(set(path_slots + query_slots + header_slots + body_slots + previous_slot_list)),
                            'previous_slot': previous_slot,
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
                            extract_slot.append({'type': 'custom', 'form': form})
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
                    form_slots.append({'name': slot.name, 'type': slot.type, 'extract_methods': extract_slot})
                data.forms.append({'name': form, 'slots': form_data})
                if validation_data != []:
                    data.actions.append({'name': f'validate_{form}', 'validation_method': True, 'info': validation_data})

                # Collect all form slots of this dialogue
                dialogue_form_slots.extend(form_data)
        for intent in intents:
            data.stories.append({
                'name': f"{name} - {intent.name}",
                'intent': intent.name,
                'responses': dialogue_responses
            })

        if dialogue_form_slots != []:
            # Find last action and add field for reseting all dialogue form slots
            data.actions[-1]["reset_slots"] = dialogue_form_slots

    # Validate and merge slots with similar name for the domain file
    form_slots = sorted(form_slots, key = itemgetter('name'))
    for k, v in groupby(form_slots, key = itemgetter('name')):
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
        data.slots.append({'name': k, 'type': type, 'extract_methods': extract_methods, 'default': None})

    # Extract Connectors
    if model.connectors:
        for connector in model.connectors:
            if connector.name == 'slack':
                data.connectors.append({
                    'name': connector.name,
                    'token': connector.token,
                    'channel': connector.channel,
                    'signing_secret': connector.signing_secret
                })
            elif connector.name == 'telegram':
                data.connectors.append({
                    'name': connector.name,
                    'token': connector.token,
                    'verify': connector.verify,
                    'webhook_url': connector.webhook_url
                })
            else:
                raise Exception(f"Connector {connector.name} is not supported")

    # Extract access control
    if model.access_control:

        # Extract Roles
        data.roles = model.access_control.roles.words
        data.ac_misc.default_role = model.access_control.roles.default

        # Extract Policies
        if model.access_control.policies:
            data.ac_misc.global_ac = True # Global access control is defined
            for policy in model.access_control.policies:
                for action in policy.actions:
                    if action in data.policies.keys():
                        data.policies[action].update(set(policy.roles))
                    else:
                        data.policies[action] = set(policy.roles)

        # Give all roles under "all_actions" keyword permission to all actions (if any)
        if ALL_ACTIONS in data.policies.keys():
            admins = data.policies.pop(ALL_ACTIONS)
            for action in data.policies.keys():
                data.policies[action].update(set(admins))

        data.policies = process_policies_dict(data.policies)

        # Extract Path
        if model.access_control.path:
            data.ac_misc.policy_path = model.access_control.path.path
        else:
            data.ac_misc.policy_path = None

        # Extract Role-Users Policies
        if model.access_control.users:
            for role in model.access_control.users.roles:
                if role.role in data.ac_misc.role_users.keys():
                    raise Exception(f"Duplicate role '{role.role}' in 'Users:'")
                data.ac_misc.role_users[role.role] = role.users

            # Write Role-User Policies in the file. The file is created if not found.
            if data.ac_misc.policy_path:    
                if not path.isabs(data.ac_misc.policy_path):
                    data.ac_misc.policy_path = path.normpath(path.join(out_dir, data.ac_misc.policy_path))
                
                directory = path.dirname(data.ac_misc.policy_path)
                if not path.exists(directory):
                    os.makedirs(directory)
            else:
                data.ac_misc.policy_path = 'user_role_mappings.txt'

            with open(path.join(out_dir, data.ac_misc.policy_path), 'w') as f:
                json.dump(data.ac_misc.role_users, f)
        else:
            if data.ac_misc.policy_path:
                if not path.isabs(data.ac_misc.policy_path):
                    data.ac_misc.policy_path = path.normpath(path.join(out_dir, data.ac_misc.policy_path))
                if not os.path.isfile(data.ac_misc.policy_path):
                    raise Exception(f'File not found: {data.ac_misc.policy_path}')
            else:
                raise Exception(f"Both 'Users' and 'Path' were not defined")

        # Extract Authentication method
        if model.access_control.authentication.method == 'slot':
            if not model.access_control.authentication.slot_name:
                raise Exception("You need to provide a 'slot_name' for this authentication method")

            data.ac_misc.authentication['method'] = model.access_control.authentication.method
            data.ac_misc.authentication['slot_name'] = model.access_control.authentication.slot_name
        else:
            if model.access_control.authentication.slot_name:
                print("WARNING: 'slot_name' is not applicable to this authentication method")

            data.ac_misc.authentication['method'] = model.access_control.authentication.method


    # Validate access control
    data = validate_access_control(data, model)

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
        elif phrase.__class__.__name__ == 'GlobalSlotRef':
            slots.append(phrase.slot.name)
            message.extend(["{", f"{phrase.slot.name}", "}"])
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
        result = f"'{param}'"
        return result, [], [], []
    elif param.__class__.__name__ == 'Dict':
        result = '{'
        for item in param.items:
            item_results, item_slots, item_user_properties, item_system_properties = process_parameter_value(item.value)
            slots.extend(item_slots)
            user_properties.extend(item_user_properties)
            system_properties.extend(item_system_properties)
            result = result + f"'{item.name}': {item_results}, "
        # Omit last comma
        result = result[:-2]
        result = result + '}'
    elif param.__class__.__name__ == 'List':
        result = '['
        for item in param.items:
            item_results, item_slots, item_user_properties, item_system_properties = process_parameter_value(item)
            slots.extend(item_slots)
            user_properties.extend(item_user_properties)
            system_properties.extend(item_system_properties)
            result = result + item_results + ','
        # Omit last comma
        result = result[:-1]
        result = result + ']'
    elif param.__class__.__name__ == 'FormParamRef':
        new_slot = ['f"{', f"{param.param.name}", '}"']
        result = ''.join(new_slot)
        slots.append(f"{param.param.name}")
    elif param.__class__.__name__ == 'GlobalSlotRef':
        new_slot = ['f"{', f"{param.slot.name}", '}"']
        result = ''.join(new_slot)
        slots.append(f"{param.slot.name}")
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
        results = results + f"'{param.name}': "
        if param.value.__class__.__name__ == 'Dict':
            dict_results = '{'
            for item in param.value.items:
                item_results, item_slots, item_user_properties, item_system_properties = process_eservice_params(item.value)
                slots.extend(item_slots)
                user_properties.extend(item_user_properties)
                system_properties.extend(item_system_properties)
                dict_results = dict_results + f"'{item.name}': {item_results}, "
            if len(dict_results) > 1:
                dict_results = dict_results[:-2]
            dict_results = dict_results + '}'
            results = results + f"{dict_results}, "
        elif param.value.__class__.__name__ == 'List':
            list_results = '['
            list_length = len(param.value.items)
            for item in param.value.items:
                item_results, item_slots, item_user_properties, item_system_properties = process_eservice_params(item)
                slots.extend(item_slots)
                user_properties.extend(item_user_properties)
                system_properties.extend(item_system_properties)
                list_results = list_results + item_results + ', '
            if len(list_results) > 1:
                list_results = list_results[:-2]
            list_results = list_results + ']'
            results = results + f"{list_results}, "
        else:
            param_result, param_slots, param_user_properties, param_system_properties = process_parameter_value(param.value)
            slots.extend(param_slots)
            user_properties.extend(param_user_properties)
            system_properties.extend(param_system_properties)
            results = results + param_result + ', '
    # Omit last comma and space
    if len(results) > 2:
        results = results[:-2]
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
    elif params.__class__.__name__ == 'GlobalSlotRef':
        new_slot = ["{", f"{params.slot.name}", "}"]
        slots.append(f"{params.slot.name}")
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
        elif param.value.__class__.__name__ == 'GlobalSlotRef':
            new_slot = ["{", f"{param.value.slot.name}", "}"]
            results[param.name] = ' '.join(new_slot)
            slots.append(f"{param.value.slot.name}")
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

def merge_header_mimes(header_params, mimes):
    if header_params != '{}':
        header_params = header_params[:-1] + ',' + mimes + '}'
    else:
        header_params = header_params[:-1] + mimes + '}'
    return header_params

def process_response_filter(text):
    """ Convert response filtering to template-ready string. """
    if text is None:
        return ''
    return ''.join([f"[{word}]" if word.isnumeric() else f"[\'{word}\']" for word in text.split('.')])

def process_policies_dict(policies: Dict) -> Dict:
    ''' Process policy names '''

    # Format the name of the actions to avoid KeyErrors
    policies_new = {}
    for policy_name in policies.keys():
        policies_new[f'action_{policy_name}'] = policies.get(policy_name)

    return policies_new

def validate_path_params(url, path_params):
    ''' Check whether all path_params keys and params in url match. '''
    url_params = re.findall("{[a-z|A-Z]+}", url)
    url_params = [url[1:-1] for url in url_params]  # Discard brackets
    return set(url_params) == set(path_params.keys())

def validate_access_control(data: TransformationDataModel, model) -> TransformationDataModel:
    ''' Validate access control parameters. '''
    if model.access_control:
        # Check if default role is defined
        if data.ac_misc.default_role not in data.roles:
            data.roles.append(data.ac_misc.default_role)
            print(f"WARNING: Default role '{data.ac_misc.default_role}' is not defined under 'Roles:'")

        actionGroup_roles = []
        action_roles = []

        if data.ac_misc.global_ac:
            actionGroup_roles = unpack_nested_dict(data.policies)

            # Check if roles assinged to actionGroups are defined
            for role in actionGroup_roles:
                if role not in data.roles:
                    raise Exception(f"Role '{role}' is not defined under 'Roles:'")

            # Check if action names are the same in data.actions and policies
            data_actions = [action["name"] for action in data.actions]

            for action in data.policies.keys():
                if action not in data_actions:
                    policy_name = ""
                    for policy in model.access_control.policies:
                        for action_p in policy.actions:
                            if action == f"action_{action_p}":
                                policy_name = policy.name
                    raise Exception(f"Action: {action} in Policy: {policy_name} is not a defined ActionGroup")

        if data.ac_misc.local_ac:
            # Check if roles assigned to actions are defined
            for actionGroup in data.actions:
                if 'actions' in actionGroup.keys():
                    for action in actionGroup['actions']:
                        if 'roles' in action.keys():
                            action_roles.extend(action['roles'])
            for role in action_roles:
                if role not in data.roles:
                    raise Exception(f"Role '{role}' is not defined under 'Roles:'")

        # Check if all defined roles are assigned to at least one actionGroup or action
        for role in data.roles:
            if role not in action_roles and role not in actionGroup_roles and role != data.ac_misc.default_role:
                print(f"WARNING: Role '{role}' is defined but not used")

        # Check if the authentication slot exists in the bot's slots, if slot auth is selected
        if data.ac_misc.authentication['method'] == 'slot':
            slot_names = [slot['name'] for slot in data.slots]
            if data.ac_misc.authentication['slot_name'] not in slot_names:
                raise Exception(f"Authentication slot {data.ac_misc.authentication['slot_name']} not defined in Dialogues")

        # Check if third-party authentication is required, but no third-party connector is defined
        if data.ac_misc.authentication['method'] not in ['slot', 'user_id']:
            connector_names = [connector['name'] for connector in data.connectors]
            if data.ac_misc.authentication['method'] not in connector_names:
                raise Exception(f"You need to define a '{data.ac_misc.authentication['method']}' connector to use this authentication method")

    elif data.ac_misc.local_ac:
        # Check if local_ac is defined, but no access control is defined
        raise Exception("You need to define 'access controls' rule first, to use local access control")

    return data

def unpack_nested_dict(dic: Dict[Any, Dict]) -> Set:
    ''' Unpack the values of a nested dictionary. Duplicate values are discarded. '''

    values = set()
    for v in dic.values():
        for val in v:
            values.add(val)
    return values
