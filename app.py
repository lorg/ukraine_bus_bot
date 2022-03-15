import logging

from flask import jsonify, Flask, make_response, request, Response, redirect  # type: ignore

from environment import Environment
from messaging_bot import start_bot

app = Flask(__name__)
_env = Environment()


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_env():
    return _env


@app.route('/')
def hello_world() -> Response:
    return jsonify({'message': 'hello world!'})


@app.route('/blast/<string:webhook_token>')
def blast(webhook_token):
    env = get_env()
    if webhook_token != env.WEBHOOK_TOKEN:
        print(f"webhook token: received: {webhook_token} != expected: {env.WEBHOOK_TOKEN}")
        return jsonify({"error": "incorrect token"})
    with start_bot() as bot:
        bot.handle_blast_request()


@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)
