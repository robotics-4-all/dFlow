import json
import os
import pathlib
from os.path import join
from typing import Any

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

from dflow.definitions import THIS_DIR, MODEL_REPO_PATH, BUILTIN_MODELS

pretty.install()

CURRENT_FPATH = pathlib.Path(__file__).parent.resolve()

GLOBAL_REPO = GlobalModelRepository()


def verify_component_names(model):
    _ids = []
    components = model.components
    for b in components:
        if b.name in _ids:
            raise TextXSemanticError(
                f"Component with name <{b.name}> already exists", **get_location(b)
            )
        _ids.append(b.name)


def verify_broker_names(model):
    _ids = []
    brokers = get_children_of_type("MQTTBroker", model)
    brokers += get_children_of_type("AMQPBroker", model)
    brokers += get_children_of_type("RedisBroker", model)
    for b in brokers:
        if b.name in _ids:
            raise TextXSemanticError(
                f"Broker with name <{b.name}> already exists", **get_location(b)
            )
        _ids.append(b.name)


def model_proc(model, metamodel):
    verify_broker_names(model)
    verify_component_names(model)


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
        join(THIS_DIR, 'grammar', 'dflow.tx'),
        classes=class_provider,
        auto_init_attributes=True,
        textx_tools_support=True,
        # global_repository=GLOBAL_REPO,
        global_repository=global_repo,
        debug=debug,
    )

    metamodel.register_scope_providers(get_scode_providers())
    metamodel.register_model_processor(model_proc)
    metamodel.register_obj_processors(obj_processors)
    return metamodel


def get_scode_providers():
    sp = {"*.*": scoping_providers.FQNImportURI(importAs=True)}
    if BUILTIN_MODELS:
        sp["brokers*"] = scoping_providers.FQNGlobalRepo(
            join(BUILTIN_MODELS, "broker", "*.dflow"))
        # sp["entities*"] = scoping_providers.FQNGlobalRepo(
        #     join(BUILTIN_MODELS, "entity", "*.dflow"))
    if MODEL_REPO_PATH:
        sp["brokers*"] = scoping_providers.FQNGlobalRepo(
            join(MODEL_REPO_PATH, "broker", "*.dflow"))
        # sp["entities*"] = scoping_providers.FQNGlobalRepo(
        #     join(MODEL_REPO_PATH, "entity", "*.dflow"))
    return sp


def build_model(model_path: str, debug: bool = False):
    # Parse model
    mm = get_metamodel(debug=debug)
    model = mm.model_from_file(model_path)
    return model


@language("dflow", "*.dflow")
def dflow_language():
    "DFlow DSL for building intent-based Virtual Assistants (VAs)"
    mm = get_metamodel()
    return mm
