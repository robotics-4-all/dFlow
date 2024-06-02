from typing import List
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

from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY
)

from dflow.language import build_model, merge_models
from dflow.generator import codegen as rasa_generator

from dflow import definitions as CONSTANTS

API_KEY = os.getenv("API_KEY", "123")

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


if not os.path.exists(CONSTANTS.TMP_DIR):
    try:
        os.mkdir(CONSTANTS.TMP_DIR)
    except Exception as e:
        print(e)


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
    fpath = os.path.join(CONSTANTS.TMP_DIR, f"model_for_validation-{u_id}.dflow")
    with open(fpath, "w") as f:
        f.write(text)
    try:
        build_model(fpath)
        out_path = rasa_generator(
            fpath,
            output_path=os.path.join(CONSTANTS.TMP_DIR, f'codegen-{u_id}')
        )
        print("Model validation success!!")
        resp["message"] = "Model validation success"
    except Exception as e:
        print(f"Exception while validating model: {e}")
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
    fpath = os.path.join(CONSTANTS.TMP_DIR, f"model_for_validation-{u_id}.dflow")
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
    fpath = os.path.join(CONSTANTS.TMP_DIR, f"model_for_validation-{u_id}.dflow")
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


@api.post("/merge")
async def merge(models: list[UploadFile], api_key: str = Security(get_api_key)) -> FileResponse:
    if not len(models):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Model storage is empty!",
        )
    try:
        model_content = [(await file.read()).decode("utf-8") for file in models]
        merged_model = merge_models(model_content)
        merged_model_path = os.path.join(
            CONSTANTS.TMP_DIR,
            f'merged-{uuid.uuid4().hex[0:8]}.dflow'
        )
        with open(merged_model_path, "w") as f:
            f.write(merged_model)
        return FileResponse(
            merged_model_path,
            filename=os.path.basename(merged_model_path)
        )
    except Exception as e:
        print(f"Exception while merging dflow models\n{e}")
        raise HTTPException(status_code=400, detail=f"Codegen error: {e}")

@api.post("/generate/file")
async def gen_from_file(model_file: UploadFile = File(...),
                        api_key: str = Security(get_api_key)):
    try:
        fd = model_file.file
        uid = uuid.uuid4().hex[0:8]
        fpath = os.path.join(
            CONSTANTS.TMP_DIR,
            f"model_for_codegen-{uid}.dflow"
        )
        with open(fpath, "wb") as f:
            f.write(fd.read())
        out_path = rasa_generator(
            fpath,
            output_path=os.path.join(CONSTANTS.TMP_DIR, f'codegen-{uid}')
        )
        tarball_path = os.path.join(
            CONSTANTS.TMP_DIR,
            f'codegen-{uid}.tar.gz'
        )
        make_tarball(out_path, tarball_path)
        return FileResponse(tarball_path,
                            filename=os.path.basename(tarball_path),
                            media_type='application/x-tar')
    except Exception as e:
        print(f"Exception while generating rasa sources\n{e}")
        raise HTTPException(status_code=400, detail=f"Codegen error: {e}")


@api.post("/generate/b64")
async def gen_model_b64(fenc: str = '', api_key: str = Security(get_api_key)):
    model_dec = base64.b64decode(fenc)
    try:
        uid = uuid.uuid4().hex[0:8]
        fpath = os.path.join(
            CONSTANTS.TMP_DIR,
            f"model_for_codegen-{uid}.dflow"
        )
        with open(fpath, 'w') as f:
            f.write(model_dec)
        out_path = rasa_generator(
            fpath,
            output_path=os.path.join(CONSTANTS.TMP_DIR, f'codegen-{uid}')
        )
        tarball_path = os.path.join(
            CONSTANTS.TMP_DIR,
            f'codegen-{uid}.tar.gz'
        )
        make_tarball(out_path, tarball_path)
        return FileResponse(tarball_path,
                    filename=os.path.basename(tarball_path),
                    media_type='application/x-tar')
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"{str(e)}",
        )

@api.post("/generate")
async def gen_model(input_model: TransformationModel = Body(...),
                    api_key: str = Security(get_api_key)):
    try:
        uid = uuid.uuid4().hex[0:8]
        fpath = os.path.join(
            CONSTANTS.TMP_DIR,
            f"model_for_codegen-{uid}.dflow"
        )
        with open(fpath, 'w') as f:
            f.write(input_model.model)
        out_path = rasa_generator(
            fpath,
            output_path=os.path.join(CONSTANTS.TMP_DIR, f'codegen-{uid}')
        )
        tarball_path = os.path.join(
            CONSTANTS.TMP_DIR,
            f'codegen-{uid}.tar.gz'
        )
        make_tarball(out_path, tarball_path)
        return FileResponse(tarball_path,
                    filename=os.path.basename(tarball_path),
                    media_type='application/x-tar')
    except Exception as e:
        print(f"Exception thrown in /generate: {e}")
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"{str(e)}",
        )


def make_tarball(source_dir, out_path):
    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))
