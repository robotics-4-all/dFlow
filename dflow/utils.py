import os
import requests
from os.path import dirname, join
from textx import metamodel_from_file
import textx.scoping.providers as scoping_providers


this_dir = dirname(__file__)

API_KEY = os.getenv("API_KEY", "123")

def get_mm(debug=False, global_scope=True):
    mm = metamodel_from_file(
        join(this_dir, 'grammar', 'dflow.tx'),
        global_repository=global_scope,
        debug=debug
    )

    mm.register_scope_providers(
        {
            "*.*": scoping_providers.FQNImportURI(
                importAs=True,
            )
        }
    )

    return mm


def build_model(model_fpath):
    mm = get_mm(global_scope=True)
    model = mm.model_from_file(model_fpath)
    # print(model._tx_loaded_models)
    reg_models = mm._tx_model_repository.all_models.filename_to_model
    models = [val for _, val in reg_models.items() if val != model]
    return (model, models)


def get_grammar():
    with open(join(this_dir, 'grammar', 'dflow.tx')) as f:
        return f.read()

def llm_invoke(system_prompt: str = '', messages: list = [], temperature: float = 0):
    try:
        response = requests.post(
            "https://services.issel.ee.auth.gr/llms/chat",
            headers={
                'access_token': API_KEY
            },
            json={
                "system_prompt": system_prompt,
                "messages": messages
            },
            params={
                "temperature": temperature
            }
        )
        return response.json()['text']
    except Exception as e:
        detail = f"Could not reach LLM service: {e}"
        print(detail)
        raise ValueError(detail)

def create_user_prompt_message(prompt: str) -> dict:
    return {
        "role": "user",
        "prompt": prompt
    }

def create_assistant_prompt_message(prompt: str) -> dict:
    return {
        "role": "assistant",
        "prompt": prompt
    }



if __name__ == '__main__':
    description = 'Get user details'
    summary = None
    system_prompt = "You are an NLP engineer expert assisting users to create VAs. Each VA scenario calls a specific API that has a description and possibly a summary. Your task is to create a set of 10 diverse intent examples based on the description and summary. The examples should be human-like, varied, and cover different ways the same intent might be expressed. Return a Python list of strings containing only the requested intent examples. Avoid any other text or preamble."
    _prompt = ''
    if description:
        _prompt += f"Description: {description} "
    if summary:
        _prompt += f"Description: {summary} "
    msg = create_user_prompt_message(_prompt)
    response = llm_invoke(system_prompt, messages=[msg])
    print(response)