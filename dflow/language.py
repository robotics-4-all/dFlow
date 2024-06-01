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
    seen = set()
    for item in input_list:
        if item in seen:
            return True
        seen.add(item)
    return False


def _validate_model(model):
    """ Runs semantic validation on the provided model and raises Errors. """

    all_concept_names = []
    intents = get_children_of_type("Intent", model)
    if len(intents) < 1:
        raise TextXSemanticError("There must be at least 1 Intent provided!")
    intents_names = [i.name for i in intents]
    if has_duplicates(intents_names):
        raise TextXSemanticError("Intents IDs have duplicate values!")
    all_concept_names.extend(intents_names)

    # Validate for at least 2 examples per intent
    for intent in intents:
        if len(intent.phrases) < 2:
            raise TextXSemanticError(f'Only {len(intent.phrases)} given in intent {intent}! At least 2 are needed!')

    entities = get_children_of_type("TrainableEntity", model)
    entities_names = [e.name for e in entities]
    if has_duplicates(entities_names):
        raise TextXSemanticError("Entities IDs have duplicate values!")
    all_concept_names.extend(entities_names)

    synonyms = get_children_of_type("Synonym", model)
    synonyms_names = [s.names for s in synonyms]
    if has_duplicates(synonyms_names):
        raise TextXSemanticError("Synonyms IDs have duplicate values!")
    all_concept_names.extend(synonyms_names)

    dialogues = get_children_of_type("Dialogue", model)
    if not len(dialogues):
        raise TextXSemanticError("There must be at least 1 Dialogue!")

    dialogues_names = [d.name for d in dialogues]
    if has_duplicates(dialogues_names):
        raise TextXSemanticError("Dialogues IDs have duplicate values!")
    all_concept_names.extend(dialogues_names)

    responses_names = [resp.name for d in dialogues for resp in d.responses]
    if has_duplicates(responses_names):
        raise TextXSemanticError("Responses IDs have duplicate values!")
    all_concept_names.extend(responses_names)

    gslots = get_children_of_type("GlobalSlot", model)
    gslots_names = [gs.name for gs in gslots]
    if has_duplicates(gslots_names):
        raise TextXSemanticError("GSlots IDs have duplicate values!")
    all_concept_names.extend(gslots_names)

    events = get_children_of_type("Event", model)
    events_names = [e.name for e in events]
    if has_duplicates(events_names):
        raise TextXSemanticError("Events IDs have duplicate values!")
    all_concept_names.extend(events_names)

    eservices = get_children_of_type("EServiceDefHTTP", model)
    eservices_names = [e.name for e in eservices]
    if has_duplicates(eservices_names):
        raise TextXSemanticError("EService IDs have duplicate values!")
    all_concept_names.extend(eservices_names)

    if has_duplicates(all_concept_names):
        raise TextXSemanticError("IDs among different concepts have duplicate values!")
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
