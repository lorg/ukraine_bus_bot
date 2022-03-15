# pylint: disable=too-many-lines

import re
import json
import urllib
import datetime
import logging
from typing import Dict, Any, List, Optional

from flask.testing import FlaskClient  # type: ignore

import db
import conftest

import texts
from texts import Inputs
import utils

from messaging import Message, MockMessagingSession
import models


GenDict = Dict[str, Any]


def print_events(session):
    print("\nevents:\n\n")
    for event in session.sent_events:
        print(event)
        print("\n\n")


def print_messages(session):
    print("\nmessages:\n\n")
    for message in session.sent_messages:
        print(message)
        print("\n\n")


def test_sanity(client):
    result = client.get('/')
    assert result.json and result.json.get('message') == 'hello world!'
