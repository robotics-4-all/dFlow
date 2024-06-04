import json
import os
import pathlib
from os.path import join
from typing import Any, List
import uuid

import textx.scoping.providers as scoping_providers
from rich import pretty, print
from textx import (
    TextXSemanticError,
    get_children_of_type,
    language,
    metamodel_from_file,
    get_location,
)
from textx.scoping import GlobalModelRepository, ModelRepository

import dflow.definitions as CONSTANTS

from dflow.generator import validate_path_params, process_eservice_params_as_dict

pretty.install()

CURRENT_FPATH = pathlib.Path(__file__).parent.resolve()

GLOBAL_REPO = GlobalModelRepository()


def model_proc(model, metamodel):
    pass


CUSTOM_CLASSES = [
]


def class_provider(name):
    classes = dict(map(lambda x: (x.__name__, x), CUSTOM_CLASSES))
    return classes.get(name)


def component_processor(component):
    if component.attribute == None:
        component.attribute = ""
    return component

def nid_processor(nid):
    nid = nid.replace("\n", "")
    return nid


obj_processors = {
    'NID': nid_processor,
}


def get_metamodel(debug: bool = False, global_repo: bool = False):
    metamodel = metamodel_from_file(
        join(CONSTANTS.THIS_DIR, 'grammar', 'dflow.tx'),
        classes=class_provider,
        auto_init_attributes=True,
        textx_tools_support=True,
        # global_repository=GLOBAL_REPO,
        global_repository=global_repo,
        debug=debug,
    )

    # metamodel.register_scope_providers(get_scode_providers())
    metamodel.register_model_processor(model_proc)
    metamodel.register_obj_processors(obj_processors)
    return metamodel


def get_scode_providers():
    sp = {"*.*": scoping_providers.FQNImportURI(importAs=True)}
    if CONSTANTS.BUILTIN_MODELS:
        sp["brokers*"] = scoping_providers.FQNGlobalRepo(
            join(CONSTANTS.BUILTIN_MODELS, "broker", "*.dflow"))
        # sp["entities*"] = scoping_providers.FQNGlobalRepo(
        #     join(BUILTIN_MODELS, "entity", "*.dflow"))
    if CONSTANTS.MODEL_REPO_PATH:
        sp["brokers*"] = scoping_providers.FQNGlobalRepo(
            join(CONSTANTS.MODEL_REPO_PATH, "broker", "*.dflow"))
        # sp["entities*"] = scoping_providers.FQNGlobalRepo(
        #     join(MODEL_REPO_PATH, "entity", "*.dflow"))
    return sp


def has_duplicates(input_list):
    """ Returns weather the input_list has any duplicate values, and the duplicate value. """
    seen = set()
    for item in input_list:
        if item in seen:
            return True, item
        seen.add(item)
    return False, None


def _validate_model(model):
    """ Runs semantic validation on the provided model and raises Errors. """

    all_concept_names = []
    # Validate Intents
    intents = get_children_of_type("Intent", model)
    if len(intents) < 1:
        raise TextXSemanticError("There must be at least 1 Intent provided!")
    intents_names = [i.name for i in intents]
    check, _intent = has_duplicates(intents_names)
    if check:
        raise TextXSemanticError(f"Intents ID `{_intent}` is used multiple times!")
    all_concept_names.extend(intents_names)

    # Validate for at least 2 examples per intent
    for intent in intents:
        if len(intent.phrases) < 2:
            raise TextXSemanticError(f'Only {len(intent.phrases)} given in intent {intent}! At least 2 are needed!')

    # Validate Entities
    entities = get_children_of_type("TrainableEntity", model)
    entities_names = [e.name for e in entities]
    check, _entity = has_duplicates(entities_names)
    if check:
        raise TextXSemanticError(f"Entities ID '{_entity}' is used multiple times!")
    all_concept_names.extend(entities_names)

    # Validate trainable entities examples - no duplicates among different entities
    entities_words = [e.words for e in entities]
    entities_words = [set(_words) for _words in entities_words]

    seen = set()
    value_to_sets = {}
    # Iterate through each set in the list
    for idx, s in enumerate(entities_words):
        if not len(s):
            raise Exception(f'No examples given for entity {entities_words[idx]}.')
        for item in s:
            if item in seen:
                prev_idx = value_to_sets[item][0]
                raise TextXSemanticError(f"Trainable Entity examples must exist only in one entity. Entity example `{item}` found in entity `{entities_names[idx]}` and entity `{entities_names[prev_idx]}`!")
            else:
                seen.add(item)
                if item not in value_to_sets:
                    value_to_sets[item] = [idx]

    # Validate Pretrained Entities - they must have at least one example
    pretrained_entities_examples = {}
    for intent in intents:
        for complex_phrase in intent.phrases:
            for phrase in complex_phrase.phrases:
                if phrase.__class__.__name__ == "PretrainedEntityRef":
                    name = phrase.entity
                    if name not in pretrained_entities_examples:
                        pretrained_entities_examples[name] = []
                    if phrase.refPreValues != []:
                        pretrained_entities_examples[name].extend(phrase.refPreValues)
    for pe, examples in pretrained_entities_examples.items():
        if pe not in CONSTANTS.PE_CLASSES_LIST:
            raise TextXSemanticError(f"Pretrained Entity `{pe}` is not in the supported entity classes.")
        if not len(examples):
            raise TextXSemanticError(f"No example given for Pretrained Entity `{pe}`.")

    # Validate Synonyms
    synonyms = get_children_of_type("Synonym", model)
    synonyms_names = [s.name for s in synonyms]
    check, _synonym = has_duplicates(synonyms_names)
    if check:
        raise TextXSemanticError(f"Synonyms ID `{_synonym}` is used multiple times!")
    all_concept_names.extend(synonyms_names)

    synonyms_words = [e.words for e in synonyms]
    synonyms_words = [set(_words) for _words in synonyms_words]

    seen = set()
    value_to_sets = {}
    # Iterate through each set in the list
    for idx, s in enumerate(synonyms_words):
        if not len(s):
            raise Exception(f'No examples given for synonym {entities_words[idx]}.')
        for item in s:
            if item in seen:
                prev_idx = value_to_sets[item][0]
                raise TextXSemanticError(f"Synonym phrases must exist only in one synonym. Synonym phrase `{item}` found in synonym `{synonyms_names[idx]}` and synonym `{synonyms_names[prev_idx]}`!")
            else:
                seen.add(item)
                if item not in value_to_sets:
                    value_to_sets[item] = [idx]

    # Validate EServices
    eservices = get_children_of_type("EServiceDefHTTP", model)
    eservices_names = [e.name for e in eservices]
    check, _eservice = has_duplicates(eservices_names)
    if check:
        raise TextXSemanticError(f"EService ID `{_eservice}` is used multiple times!")
    all_concept_names.extend(eservices_names)

    eservices_info = {}
    for service in eservices:
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
        eservices_info[service.name] = service_info

    # Validate Dialogues
    dialogues = get_children_of_type("Dialogue", model)
    if not len(dialogues):
        raise TextXSemanticError("There must be at least 1 Dialogue!")

    dialogues_names = [d.name for d in dialogues]
    check, _dialogue = has_duplicates(dialogues_names)
    if check:
        raise TextXSemanticError(f"Dialogues ID `{_dialogue}` is used multiple times!")
    all_concept_names.extend(dialogues_names)

    responses_names = [resp.name for d in dialogues for resp in d.responses]
    check, _response = has_duplicates(responses_names)
    if check:
        raise TextXSemanticError(f"Responses ID `{_response}` is used multiple times!")
    all_concept_names.extend(responses_names)

    for dialogue in dialogues:
        for response in dialogue.responses:
            if response.__class__.__name__ == 'ActionGroup':
                for action in response.actions:
                    if action.__class__.__name__ == 'EServiceCallHTTP':
                        path_params, _, _, _ = process_eservice_params_as_dict(action.path_params)
                        validation = validate_path_params(eservices_info[action.eserviceRef.name]['url'], path_params)
                        if not validation:
                            raise Exception(f'Service `{action.eserviceRef.name}` path and path params do not match when called in `{response.name}`.')
            else:
                for slot in response.params:
                    if slot.source.__class__.__name__ == 'EServiceCallHTTP':
                        path_params, _, _, _ = process_eservice_params_as_dict(slot.source.path_params)
                        validation = validate_path_params(eservices_info[slot.source.eserviceRef.name]['url'], path_params)
                        if not validation:
                            raise Exception(f'Service `{slot.source.eserviceRef.name}` path and path params do not match when called in `{response.name}` for slot `{slot.name}`.')

    # Validate Global Slots
    gslots = get_children_of_type("GlobalSlot", model)
    gslots_names = [gs.name for gs in gslots]
    check, _gslot = has_duplicates(gslots_names)
    if check:
        raise TextXSemanticError(f"GSlots ID `{_gslot}` is used multiple times!")
    all_concept_names.extend(gslots_names)

    # Validate Events
    events = get_children_of_type("Event", model)
    events_names = [e.name for e in events]
    check, _event = has_duplicates(events_names)
    if check:
        raise TextXSemanticError(f"Events ID `{_event}` is used multiple times!")
    all_concept_names.extend(events_names)

    # Check duplicates among all IDs
    check, _attributes = has_duplicates(all_concept_names)
    if check:
        raise TextXSemanticError(f"ID `{_attributes}` is used multiple times in different concepts!")
    return


def build_model(model_path: str, debug: bool = False):
    # Parse model
    mm = get_metamodel(debug=debug)
    model = mm.model_from_file(model_path)
    _validate_model(model)
    return model


def report_model_info(model):
    entities = get_children_of_type("TrainableEntity", model)
    synonyms = get_children_of_type("Synonym", model)
    gslots = get_children_of_type("GlobalSlot", model)
    intents = get_children_of_type("Intent", model)
    events = get_children_of_type("Event", model)
    eservices = get_children_of_type("EServiceDefHTTP", model)
    dialogues = get_children_of_type("Dialogue", model)
    access_control = get_children_of_type("AccessControlDef", model)
    connectors = get_children_of_type("Slack", model) + get_children_of_type("Telegram", model)
    print(f"Trainable Entities: {[e.name for e in entities]}")
    print(f"Synonyms: {[s.name for s in synonyms]}")
    print(f"Global Slots: {[gs.name for gs in gslots]}")
    print(f"Intents: {[i.name for i in intents]}")
    print(f"Events: {[e.name for e in events]}")
    print(f"External Services: {[e.name for e in eservices]}")
    print(f"Dialogues: {[d.name for d in dialogues]}")
    print(f"Access Control: {True if access_control else False}")
    print(f"Connectors: {[c.name for c in connectors]}")


@language("dflow", "*.dflow")
def dflow_language():
    "DFlow DSL for building intent-based Virtual Assistants (VAs)"
    mm = get_metamodel()
    return mm


def merge_models(models: List[Any], output: bool = False):
    sections = [
        'entities',
        'synonyms',
        'gslots',
        'triggers',
        'dialogues',
        'eservices'
    ]
    merged_strings = {k: '' for k in sections}

    for model in models:
        # Use list os sections to find keywords in file
        indexes = []
        for section in sections:
            i = model.find(section)
            indexes.append(i)
        # Sort sections based on appearance in file
        indexes, sections = zip(*sorted(zip(indexes, sections)))

        # Extract each section in reverse order
        for i in reversed(range(len(indexes))):
            ind = indexes[i]
            # ind == -1 if keyword doesn't exist in model
            if ind >= 0:
                part = model[ind:]
                model = model[:ind]
                end_i = part.rfind('end')
                merged_strings[sections[i]] += part[len(sections[i]):end_i]

    # Add section name the begining and 'end' in the end of each section
    for section in merged_strings:
        merged_strings[section] = section + merged_strings[section] + '\nend'
    merged_str = '\n\n'.join([
        merged_strings['gslots'],
        merged_strings['entities'],
        merged_strings['synonyms'],
        merged_strings['triggers'],
        merged_strings['eservices'],
        merged_strings['dialogues'],
    ])

    if output:
        gen_path = os.path.join(CONSTANTS.TMP_DIR,
                                f'model-merged-{uuid.uuid4().hex[0:8]}.dflow')
        with open(gen_path, 'w') as f:
            f.write(merged_str)
        return gen_path
    return merged_str
