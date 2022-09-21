from os import path, mkdir, getcwd, chmod
from textx import generator, metamodel_from_file
import jinja2, argparse

from textxjinja import textx_jinja_generator
import textx.scoping.providers as scoping_providers
# this_folder = dirname(__file__)

mm = metamodel_from_file('dflow.tx')
mm.register_scope_providers(
        {
            "*.*": scoping_providers.FQN()
        }
    )
model = mm.model_from_file('../examples/simple.dflow')



@generator('dflow', 'rasa')
def dflow_generate_rasa(metamodel, model, output_path, overwrite, debug, **custom_args):
    "Generator for generating rasa from dflow descriptions"
    process(model)

def process(model):
    print(model)
    data = {}
    return data

