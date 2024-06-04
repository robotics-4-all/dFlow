from os.path import dirname, join


THIS_DIR = dirname(__file__)
TEMPLATES_PATH = join(THIS_DIR, "templates")
MODEL_REPO_PATH = None
BUILTIN_MODELS = None
TMP_DIR = "/tmp/dflow"
PE_CLASSES_LIST = [
    'PERSON',
    'NORP',
    'FAC',
    'ORG',
    'GPE',
    'LOC',
    'PRODUCT',
    'EVENT',
    'WORK_OF_ART',
    'LAW',
    'LANGUAGE',
    'DATE',
    'TIME',
    'PERCENT',
    'MONEY',
    'QUANTITY',
    'ORDINAL',
    'CARDINAL'
]
