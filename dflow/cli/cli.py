import click
import os
from rich import print, pretty
import json

from dflow.language import build_model, report_model_info

pretty.install()


def make_executable(path):
    mode = os.stat(path).st_mode
    mode |= (mode & 0o444) >> 2  # copy R bits to X
    os.chmod(path, mode)


@click.group()
@click.pass_context
def cli(ctx):
    ctx.ensure_object(dict)


@cli.command("validate", help="Model Validation")
@click.pass_context
@click.argument("model_path")
def validate(ctx, model_path):
    model = build_model(model_path)
    print("[*] Model validation success!!")
    report_model_info(model)


@cli.command("gen", help="M2T/M2M transformations")
@click.pass_context
@click.argument("model_path")
@click.argument("generator")
def generate(ctx, model_path, generator):
    if generator not in ("rasa"):
        print(f"[*] Generator {generator} not supported")
        return
    if generator == "rasa":
        model = build_model(model_path)
        _model = rasa_generator(model)
        filepath = f"dflow-{model.metadata.name}.json"
        with open(filepath, "w") as fp:
            json.dump(_model, fp)
    print(f"[*] M2T finished. Output: {filepath}")


def main():
    cli(prog_name="dflow")
