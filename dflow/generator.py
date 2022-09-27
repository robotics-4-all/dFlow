from os import path, mkdir, getcwd, chmod
from textx import generator, metamodel_from_file
import jinja2, argparse, itertools

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
    stories: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    rules: List[Dict[str, Any]] = []
    slots: List[Dict[str, Any]] = []
    form_responses: List[Dict[str, Any]] = []
    form_actions: List[Dict[str, Any]] = []


@generator('dflow', 'rasa')
def dflow_generate_rasa(metamodel, model, output_path, overwrite,
        debug, **custom_args):
    "Generator for generating rasa from dflow descriptions"
    data = parse_model(model)

    # Prepare generating file directory
    if output_path is None:
        out_dir = srcgen_folder

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
                                    stories=data.stories,
                                    actions=data.actions,
                                    rules=data.rules,
                                    slots=data.slots))
        chmod(out_file, 509)
    return out_dir


def parse_model(model) -> TransformationDataModel:
    data = TransformationDataModel()
    for synonym in model.synonyms:
        data.synonyms.append({'name': synonym.name, 'words': synonym.words})

    for entity in model.entities:
        if entity.__class__.__name__ == 'PretrainedEntity':
            pass
        else:
            data.entities.append({'name': entity.name, 'words': entity.words})

    for trigger in model.triggers:
        if trigger.__class__.__name__ == 'Intent':
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
                        if name not in data.pretrained_entities:
                            data.pretrained_entities.append(name)
                        if phrase.refPreValues != []:
                            text.append(phrase.refPreValues)
            examples = [' '.join(sentence) for sentence in itertools.product(*text)]
            data.intents.append({'name': trigger.name, 'examples': examples})
        else:
            data.events.append({'name': trigger.name, 'uri': trigger.uri})

    for dialogue in model.dialogues:
        name = dialogue.name
        intent = dialogue.onTrigger.name
        responses = []
        form = []
        for response in dialogue.responses:
            responses.append(response.name)
            if response.__class__.__name__ == 'Action':
                actions = []
                for action in response.actions:
                    if action.__class__.__name__ == 'SpeakAction':
                        actions.append({
                            'type': action.__class__.__name__,
                            'text': action.text
                        })
                    elif action.__class__.__name__ == 'FireEventAction':
                        actions.append({
                            'type': action.__class__.__name__,
                            'uri': action.uri,
                            'msg': action.msg
                        })
                    elif action.__class__.__name__ == 'HTTPCallAction':
                        actions.append({
                            'type': action.__class__.__name__,
                            'host': action.host,
                            'port': action.port,
                            'path': action.path,
                            'query_params': action.query_params,
                            'path_params': action.path_params,
                            'body_params': action.body_params
                        })
                data.actions.append({"name": f"action_{response.name}", "actions": actions})
            elif response.__class__.__name__ == 'Form':
                form = response.name
                data.rules.append({
                    'name': form,
                    'intent': intent,
                    'responses': responses,
                    'form': form
                })
                for slot in response.params:
                    data.slots.append({'name': slot.name, 'type': slot.type})
                    data.form_responses.append({
                        'name': slot.name,
                        'type': slot.type,
                        'form': form,
                        'text': slot.source.ask_slot
                    })
        data.stories.append({
            'name': name,
            'intent': intent,
            'responses': responses
        })
    return data
