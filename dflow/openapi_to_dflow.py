from intent_generator import Endpoint, Operation, Parameter, RequestBody, Response, generate_intent_examples

def create_intent(operation):
    pass

def create_parameter(parameter):
    pass

def create_request_body(request_body):
    pass

def create_response(response):
    pass

def transform_to_dflow(api_elements):
    dflow_model = []
    for endpoint in api_elements:
        for operation in endpoint.operations:
            intent = create_intent(operation)
            dflow_model.append(intent)

    return dflow_model
