import logging

from flask import jsonify, Flask, make_response, request, Response, redirect  # type: ignore

import defs
from defs import TimeoutMethod
from utils import deserialize, decode_json, none_if_blank, catch_exceptions_flask, with_profiler, start_rookout, get_optional_enum_value
from environment import Environment
from messaging_bot import start_bot

app = Flask(__name__)
_env = Environment()


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_env():
    return _env


@app.route('/')
@catch_exceptions_flask
def hello_world() -> Response:
    return jsonify({'message': 'hello world!'})


@app.route('/blast/<string:webhook_token>')
@catch_exceptions_flask
def blast(webhook_token):
    env = get_env()
    if webhook_token != env.WEBHOOK_TOKEN:
        print(f"webhook token: received: {webhook_token} != expected: {env.WEBHOOK_TOKEN}")
        return jsonify({"error": "incorrect token"})
    with start_bot() as bot:
        bot.handle_blast_request()
    return jsonify({})


@app.route('/timeout/<string:timeout_params>', methods=['POST'])
@catch_exceptions_flask
def timeout(timeout_params) -> Response:

    env = get_env()
    data: dict = deserialize(timeout_params)
    if data.get('remaining_timeout_seconds'):
        remaining_timeout_seconds = data['remaining_timeout_seconds']
        if remaining_timeout_seconds > defs.MAX_TIMEOUT_SECONDS:
            timeout_seconds = defs.MAX_TIMEOUT_SECONDS
            remaining_timeout_seconds = remaining_timeout_seconds - defs.MAX_TIMEOUT_SECONDS
            data['remaining_timeout_seconds'] = remaining_timeout_seconds
        else:
            timeout_seconds = remaining_timeout_seconds
            del data['remaining_timeout_seconds']

        with start_bot() as bot:
            bot.call_timeout_with_params(data, timeout_seconds)
            return jsonify({})

    method = data.get('method')
    logger.info("timeout called with data %s and method %s",
                str(data), str(method))
    if method == TimeoutMethod.ITERATE_BLAST:
        blast_id = data.get('blast_id')
        with start_bot() as bot:
            bot.iterate_blast(blast_id)

    return jsonify({})


@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)
