import uuid
import os
import base64
import subprocess
import shutil
import tarfile
from pydantic import BaseModel

from fastapi import FastAPI, File, UploadFile, status, HTTPException, Security, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from dflow.language import build_model

API_KEY = os.getenv("API_KEY", "API_KEY")

api_keys = [API_KEY]

api = FastAPI()

api_key_header = APIKeyHeader(name="X-API-Key")


def get_api_key(api_key_header: str = Security(api_key_header)) -> str:
    if api_key_header in api_keys:
        return api_key_header
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )


api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TMP_DIR = "/tmp/dflow"


if not os.path.exists(TMP_DIR):
    os.mkdir(TMP_DIR)


class ValidationModel(BaseModel):
    name: str
    model: str


class TransformationModel(BaseModel):
    name: str
    model: str


@api.post("/validate")
async def validate(model: ValidationModel, api_key: str = Security(get_api_key)):
    text = model.model
    name = model.name
    if len(text) == 0:
        return 404
    resp = {"status": 200, "message": ""}
    u_id = uuid.uuid4().hex[0:8]
    fpath = os.path.join(TMP_DIR, f"model_for_validation-{u_id}.dflow")
    with open(fpath, "w") as f:
        f.write(text)
    try:
        build_model(fpath)
        print("Model validation success!!")
        resp["message"] = "Model validation success"
    except Exception as e:
        print(f"Exception while validating model\n{e}")
        resp["status"] = 404
        resp["message"] = str(e)
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    return resp


@api.post("/validate/file")
async def validate_file(
    file: UploadFile = File(...), api_key: str = Security(get_api_key)
):
    print(
        f"Validation for model: file=<{file.filename}>," + f" descriptor=<{file.file}>"
    )
    resp = {"status": 200, "message": ""}
    fd = file.file
    u_id = uuid.uuid4().hex[0:8]
    fpath = os.path.join(TMP_DIR, f"model_for_validation-{u_id}.dflow")
    with open(fpath, "w") as f:
        f.write(fd.read().decode("utf8"))
    try:
        model = build_model(fpath)
        print("Model validation success!!")
        resp["message"] = "Model validation success"
    except Exception as e:
        print(f"Exception while validating model\n{e}")
        resp["status"] = 404
        resp["message"] = str(e)
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    return resp


@api.post("/validate/b64")
async def validate_b64(base64_model: str, api_key: str = Security(get_api_key)):
    if len(base64_model) == 0:
        return 404
    resp = {"status": 200, "message": ""}
    fdec = base64.b64decode(base64_model)
    u_id = uuid.uuid4().hex[0:8]
    fpath = os.path.join(TMP_DIR, f"model_for_validation-{u_id}.dflow")
    with open(fpath, "wb") as f:
        f.write(fdec)
    try:
        model = build_model(fpath)
        print("Model validation success!!")
        resp["message"] = "Model validation success"
    except Exception as e:
        print(f"Exception while validating model\n{e}")
        resp["status"] = 404
        resp["message"] = str(e)
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    return resp
