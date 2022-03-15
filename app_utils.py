from flask import url_for, make_response, jsonify  # type: ignore
import environment
import utils
from texts import Text


def get_absolute_url_for(endpoint, *, include_webhook_token=True, **params):
    env = environment.Environment()
    if include_webhook_token:
        params['webhook_token'] = env.WEBHOOK_TOKEN
    apigateway_url = env.APIGATEWAY_URL
    url_path = url_for(endpoint, **params)
    if url_path.startswith('/dev'):
        url_path = utils.remove_prefix(url_path, '/dev')
        url_path = f"/{env.ENV_NAME}{url_path}"
    return f"{apigateway_url}{url_path}"


def get_absolute_onboarding_url_for(endpoint, **params):
    env = environment.Environment()
    params['web_token'] = env.WEB_TOKEN
    apigateway_url = env.APIGATEWAY_URL
    url_path = url_for(endpoint, **params)
    if url_path.startswith('/dev'):
        url_path = utils.remove_prefix(url_path, '/dev')
        url_path = f"/{env.ENV_NAME}{url_path}"
    return f"{apigateway_url}{url_path}"


def error_response(message: Text, error_code: int):
    return make_response(jsonify(dict(error=message.text)), error_code)
