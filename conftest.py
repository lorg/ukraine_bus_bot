import json
import urllib
import datetime
import dataclasses
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Union

import pytest
from flask import Flask  # type: ignore
from flask.testing import FlaskClient  # type: ignore

import db
import app
import utils
import messaging_bot
import texts_infra
import messaging
from models import MessagingMethod

from environment import Environment

# pylint: disable=redefined-outer-name

# Create python annotations for pytest @pytest.mark.local
# flag_argparse -> variable  command line flag
# action -> specifies how the command line arguments should be handled
# default -> dose the checks has to run as default
# help -> description
# skip_reason -> description
# flag_name -> the annotations ending @pytest.mark.ending,
# environments -> In what environments the test should run
# environment_check -> check if the test run on the environment specify on environments
PYTEST_FLAGS = [
    {
        'flag_argparse': '--local',
        'action': 'store_true',
        'default': False,
        'help': 'Test that can be made only in local environment',
        'flag_name': 'local',
        'skip_reason': 'done only in local mode',
        'environments': ['local'],
        'environment_check': True
    }
]


class EnvironmentsError(Exception):
    '''
    Raise error if there is an environment error
    '''

    def __init__(self, message):
        '''
        set error message
        '''
        Exception.__init__(self)
        self.message = message

    def __str__(self):
        return self.message


def pytest_addoption(parser):
    '''
    Add command line options from PYTEST_FLAGS
    '''
    for flag in PYTEST_FLAGS:
        parser.addoption(
            flag['flag_argparse'], action=flag['action'], default=flag['default'], help=flag['help']
        )


def pytest_configure(config):
    '''
    Add python annotations for pytest @pytest.mark.ending from PYTEST_FLAGS
    '''
    for flag in PYTEST_FLAGS:
        config.addinivalue_line(
            'markers', f'{flag["flag_name"]}: {flag["help"]}')


def pytest_collection_modifyitems(config, items):
    '''
    Handles pytest test and run them base on the annotations
    Also make Environment check to make sure test run on the right environment
    it is in the comments because we take the environment in tests from conftest.py
    '''
    env = Environment()
    for flag in PYTEST_FLAGS:
        if not config.getoption(flag['flag_argparse']):
            skip_test = pytest.mark.skip(reason=flag['skip_reason'])
            for item in items:
                if flag['flag_name'] in item.keywords:
                    item.add_marker(skip_test)
        else:
            if flag['environment_check']:
                if env.ENV_NAME not in flag['environments']:
                    raise EnvironmentsError(
                        f'Environment error env is:{env.ENV_NAME} but test need to run on {flag["environments"]}')


def get_local_environment_tests():
    '''
    Pre set environment variables for tests
    '''
    env = Environment()
    env.ENV_NAME = 'local'
    env.TAGS_TABLE = 'tags-table-local'
    env.ENDPOINT = 'http://127.0.0.1:6713'
    return env


@dataclasses.dataclass
class TimeoutCall:
    params: dict
    timeout_seconds: int
    call_time: datetime.datetime


class TestingBot(messaging_bot.Bot):
    messaging_session: messaging.MockMessagingSession

    def __init__(
            self,
            flask_client: FlaskClient,
            whatsapp_messaging_session: messaging.WassengerSession,
            sms_messaging_session: messaging.MessagingSession,
            table_class,
            model_table_class,
            environment: Environment):
        super().__init__(whatsapp_messaging_session, sms_messaging_session,
                         table_class=table_class, model_table_class=model_table_class, environment=environment)
        self.pending_timeouts: List[TimeoutCall] = []
        self.immediate_timeouts = True
        self.flask_client = flask_client
        self._set_call_durations: Dict[str, int] = {}

    def reset_state(self):
        self._inputs = None

    def call_timeout_with_params(self, params, timeout_seconds):
        if not self.immediate_timeouts:
            self.pending_timeouts.append(TimeoutCall(
                params, timeout_seconds, datetime.datetime.utcnow()))
            return
        self._process_single_timeout(params, timeout_seconds)

    def process_pending_timeouts(self):
        for timeout_call in self.pending_timeouts:
            self._process_single_timeout(
                timeout_call.params, timeout_call.timeout_seconds)
        self.pending_timeouts = []

    # pylint: disable=unused-argument
    def _process_single_timeout(self, params, timeout_seconds):
        timeout_params = utils.serialize(params)
        self.flask_client.post(f'/timeout/{timeout_params}')

    def say(self, user_dict, what, method: MessagingMethod = MessagingMethod.WHATSAPP):
        webhook_token = self.env.WEBHOOK_TOKEN
        if method == MessagingMethod.WHATSAPP:
            self.flask_client.post(f"/whatsapp_response/{webhook_token}", json={
                'event': "message:in:new",
                'data': {
                    'fromNumber': user_dict['phone'],
                    'body': what,
                    'chat': {'contact': {'displayName': user_dict['name']}}
                }
            })
        elif method == MessagingMethod.SMS:
            self.flask_client.post(f"/sms_response/{webhook_token}", data={
                'From': user_dict['phone'],
                'Body': what,
            })

    def send_contact(self, user_dict, contact_name, contact_phone):
        webhook_token = self.env.WEBHOOK_TOKEN
        self.flask_client.post(f"/whatsapp_response/{webhook_token}", json={
            'event': "message:in:new",
            'data': {
                'fromNumber': user_dict['phone'],
                'body': None,
                'chat': {'contact': {'displayName': user_dict['name']}},
                'contacts': [
                    dict(
                        formattedName=contact_name,
                        phones=[dict(number=contact_phone)]
                    )
                ]
            }
        })

    def clear_sent_messages(self):
        self.whatsapp_messaging_session.clear_sent_messages()
        self.sms_messaging_session.clear_sent_messages()


@ pytest.fixture
def client():
    with app.app.test_client() as test_client:
        with app.app.app_context():
            pass
        yield test_client


def create_testing_bot(flask_client, bot_class=TestingBot, admin_numbers=None, testing_numbers=None) -> TestingBot:
    env = app.Environment()
    env.ENV_NAME = 'test'
    env.SOURCE_NUMBER = 'SOURCE_NUMBER'
    # env.OTHER_NUMBER = 'OTHER_NUMBER'
    # env.FORWARD_NUMBER = 'FORWARD_NUMBER'
    # env.RUN_ROOKOUT = 0
    env.WEBHOOK_TOKEN = 'abcdef'
    # env.WEB_TOKEN = 'abcdef'
    # if admin_numbers is not None:
    #     env.ADMIN_NUMBERS = admin_numbers
    # else:
    #     env.ADMIN_NUMBERS = ['admin-number1']
    # if testing_numbers is not None:
    #     env.TESTING_NUMBERS = testing_numbers
    # else:
    #     env.TESTING_NUMBERS = ['testing-number1']
    env.SOURCE_DEVICE = 'source-device'
    # env.ADMIN_MESSAGES_SOURCE_DEVICE = 'admin-messages-source-device'

    whatsapp_messaging_session = messaging.MockWassengerSession(
        queue_messages=False, environment=env)
    sms_messaging_session = whatsapp_messaging_session

    app_bot = bot_class(
        flask_client,
        whatsapp_messaging_session,
        sms_messaging_session,
        db.MockDynamoDBTable,
        db.MockDynamoDBModelTable,
        env)

    return app_bot


@ pytest.fixture
def flask_app():
    orig_testing = app.app.testing
    app.app.testing = True
    yield app.app
    app.app.testing = orig_testing


@ pytest.fixture
def flask_client(flask_app: Flask):
    # pylint: disable=redefined-outer-name
    with flask_app.test_client() as client:
        yield client


# @pytest.fixture
# def bot(flask_client):
#     yield


@ pytest.fixture
def bot(flask_client):

    testing_bot = create_testing_bot(flask_client)

    def get_env():
        return testing_bot.env

    # pylint: disable=unused-argument
    @ contextmanager
    def new_start_bot(*args, **kwargs):
        testing_bot.post_init()  # pylint: disable=protected-access
        try:
            yield testing_bot
        finally:
            testing_bot.flush_messages()

    with new_start_bot() as testing_bot:
        orig_get_env = app.get_env
        app.get_env = get_env
        orig_start_bot = app.start_bot
        app.start_bot = new_start_bot
        yield testing_bot
        app.start_bot = orig_start_bot
        app.get_env = orig_get_env


def find_expected_messages(where: Union[TestingBot, messaging.MessagingSession], to_phone: Optional[str] = None, text_to_find: str = None, to_group: Optional[str] = None) -> List[messaging.Message]:
    if isinstance(where, TestingBot):
        result = list(where.whatsapp_messaging_session.sent_messages)
        if where.sms_messaging_session is not where.whatsapp_messaging_session:
            result = list(where.sms_messaging_session.sent_messages)
    elif isinstance(where, messaging.MessagingSession):
        result = list(where.sent_messages)
    if to_phone is not None:
        result = [message for message in result if message.phone == to_phone]
    if to_group is not None:
        result = [message for message in result if message.group == to_group]
    if text_to_find is not None:
        result = [message for message in result if text_to_find in message.message]
    return result


def find_expected_message(where: Union[TestingBot, messaging.MessagingSession], to_phone: Optional[str], text_to_find: str, to_group: Optional[str] = None) -> Optional[messaging.Message]:
    if isinstance(where, TestingBot):
        messages = list(where.whatsapp_messaging_session.sent_messages)
        if where.sms_messaging_session is not where.whatsapp_messaging_session:
            messages += list(where.sms_messaging_session.sent_messages)
    elif isinstance(where, messaging.MessagingSession):
        messages = list(where.sent_messages)
    for message in messages:
        if to_phone is not None:
            if message.phone != to_phone:
                continue
        if to_group is not None:
            if message.group != to_group:
                continue
        if text_to_find in message.message:
            return message
    return None


def get_user_messages(where: Union[TestingBot, messaging.MessagingSession], phone: str) -> List[messaging.Message]:
    '''
    Debug function get TestingBot or messaging.MessagingSession object, and phone
    return all the messages this phone recives by order
    '''
    user_messages = []
    if isinstance(where, TestingBot):
        messages = list(where.whatsapp_messaging_session.sent_messages)
        if where.sms_messaging_session is not where.whatsapp_messaging_session:
            messages += list(where.sms_messaging_session.sent_messages)
    elif isinstance(where, messaging.MessagingSession):
        messages = list(where.sent_messages)
    for message in messages:
        if message.phone == phone:
            user_messages.append(message)
    return user_messages


class Colors:
    '''
    colors class for terminal
    '''
    ENDC = '\033[0m'
    Red = "\033[31m"
    Green = "\033[32m"
    Yellow = "\033[33m"
    Blue = "\033[34m"
    Magenta = "\033[35m"
    Cyan = "\033[36m"
    White = "\033[97m"
    LightRed = "\033[91m"
    LightGreen = "\033[92m"
    LightYellow = "\033[93m"
    LightBlue = "\033[94m"


def print_log(messages, is_admin: bool = False, colors: bool = True):
    '''
    This is a debug function print log of all messages
    if is_admin true print also admin-number1 messages
    if color true
        print host messages with color the blue (host str as to be in phone)
        print admin messages with the color red
        print subscriber messages with the color green (sun str as to be in phone)
    else:
        print with no color
    '''
    for message in messages:
        if message.phone == 'admin-number1':
            if not is_admin:
                continue
        if colors:
            if 'host' in message.phone:
                color = Colors.LightBlue
                color_message = Colors.Blue
            if 'sub' in message.phone:
                color = Colors.LightGreen
                color_message = Colors.Green
            if message.phone == 'admin-number1':
                color = Colors.LightRed
                color_message = Colors.Red
            print(
                f'{color}{message.phone}:{Colors.ENDC}{color_message} {message.message}{Colors.ENDC}')
        else:
            print(f'{message.phone}: {message.message}')


def print_user_log(messages, phone, color=None):
    '''
    This is a debug function print log of all messages from phone
    if color is not None print it with color
    '''
    for message in messages:
        if message.phone == phone:
            if color is not None:
                print(f'{color}{message.phone}: {message.message}{Colors.ENDC}')
            else:
                print(f'{message.phone}: {message.message}')


@ pytest.fixture(autouse=True)
def clear_db():
    db.MockDynamoDBTable.clear_db()
    yield
    db.MockDynamoDBTable.clear_db()


@ pytest.fixture(autouse=True)
def verify_no_errors(caplog):
    yield
    for record in caplog.records:
        print(record.levelname)
        assert record.levelname != logging.ERROR
        assert record.levelname != logging.CRITICAL
