#
FROM python:3.9

#
WORKDIR /app

RUN pip install --upgrade pip

#
COPY ./requirements.txt /app/requirements.txt

#
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

#
COPY ./ /app

RUN pip install .

#
CMD ["uvicorn", "dflow.api:api", "--host", "0.0.0.0", "--port", "8080"]
