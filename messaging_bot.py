# pylint: disable=too-many-lines

import re
import uuid
import json
import random
import logging
import inspect
import datetime
import collections
import math
import copy
import secrets
from dataclasses import asdict, dataclass, field

from typing import List, Tuple, Optional, Dict, Callable, Any, Generator
from contextlib import contextmanager

import boto3  # type: ignore
import pydantic

import utils
from utils import get_optional_datetime, get_datetime, get_short_uid, serialize, is_number, create_whatsapp_link, get_uid, create_sms_link, is_phone, get_enum_value, create_shortened_link, get_random

import defs
from defs import TimeoutMethod

import app_utils
import db

import messaging
from environment import Environment
import google_sheets
from texts_infra import Text, DEFAULT_LANGUAGE_CODE, UserInput, ParseResult
from texts import Prompts, Inputs, SpecialInputTexts

from feature_flags import GlobalFeatureFlags
import models


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


APP_CODE_TTL = 5 * 60
AUTO_TOKEN_TTL = 7 * 24 * 60 * 60
SESSION_TOKEN_TTL = 7 * 24 * 60 * 60

LOOP_ITERATION_DELAY = 1


@contextmanager
def start_bot(
        whatsapp_messaging_session: Optional[messaging.WassengerSession] = None,
        #sms_messaging_session: Optional[messaging.MessagingSession] = None
) -> "Bot":

    if whatsapp_messaging_session is None:
        whatsapp_messaging_session = messaging.WassengerSession()
    # if sms_messaging_session is None:
    #     sms_messaging_session = messaging.TwilioSession()

    bot = Bot(whatsapp_messaging_session)  # , sms_messaging_session)
    try:
        yield bot
    finally:
        bot.flush_messages()


class Bot:
    def __init__(
            self,
            whatsapp_messaging_session: messaging.WassengerSession,
            # sms_messaging_session: messaging.MessagingSession,
            table_class=db.DynamoDBTable,
            model_table_class=db.DynamoDBModelTable,
            environment: Environment = Environment()):
        self.env = environment
        self.table_class = table_class

        self.blasts_table: db.DynamoDBModelTable = model_table_class(self.env.BLASTS_TABLE, models.Blast, "blast_id", "status")
        self.blast_phones_table: db.DynamoDBModelTable = model_table_class(self.env.BLAST_PHONES_TABLE, models.BlastPhone, "blast_id", "phone")

        self.whatsapp_messaging_session: messaging.WassengerSession = whatsapp_messaging_session
        # self.sms_messaging_session: messaging.MessagingSession = sms_messaging_session
        self.google_sheets = google_sheets.GoogleSheets(self.env)

        self.global_feature_flags = GlobalFeatureFlags()

    def flush_messages(self):
        self.whatsapp_messaging_session.flush_messages()
        # self.sms_messaging_session.flush_messages()

    def handle_blast_request(self):
        # phones = self.env.TEST_NUMBERS.split(',')
        phones = [line[0] for line in self.google_sheets.read_sheet()]
        text_to_send = phones[0]
        phones = phones[1:]
        blast = models.Blast(
            blast_id=utils.get_uid(),
            status=models.BlastStatus.IN_PROGRESS,
            num_phones=str(len(phones)),
            last_phone_sent_idx=0,
            started_timestamp=datetime.datetime.utcnow().isoformat(),
            ended_timestamp="",
            text_to_send=text_to_send)
        self.blasts_table.put(blast)
        with self.blast_phones_table.batch_writer() as batch:
            for i, phone in enumerate(phones):
                batch.put(models.BlastPhone(
                    blast_id=blast.blast_id,
                    phone=phone,
                    phone_idx=str(i)))
        self.whatsapp_messaging_session.send_message(phones[0], "hello world")
        self.google_sheets.report_log(self.env.SOURCE_NUMBER, phones[0], "hello world", "blast", "having a blast")
        self.call_timeout_with_params(dict(
            blast_id='BLAST_TEST_ID',
            method=defs.TimeoutMethod.ITERATE_BLAST,
        ), LOOP_ITERATION_DELAY)

    def iterate_blast(self, blast_id):
        blast = self.blasts_table.get_first(blast_id=blast_id)
        if blast is None:
            logger.log("no such blast %s", blast_id)
            return
        next_idx_to_send = int(blast.last_phone_sent_idx) + 1
        phones = self.blast_phones_table.query(blast_id=blast_id)
        idx_to_phone = {phone.phone_idx: phone.phone for phone in phones}
        phone = idx_to_phone.get(next_idx_to_send)
        if not phone:
            logger.log("no more phones to send to: %s", blast_id)
            blast.status = models.BlastStatus.DONE
            blast.ended_timestamp = datetime.datetime.utcnow().isoformat()
            self.blasts_table.put(blast)
            return

        self.whatsapp_messaging_session.send_message(phone, blast.text_to_send)
        self.google_sheets.report_log(self.env.SOURCE_NUMBER, phone, blast.text_to_send, "xxx", f"having a blast iteration {blast_id}")

        blast.last_phone_sent_idx = str(next_idx_to_send)
        self.blasts_table.put(blast)

        self.call_timeout_with_params(dict(
            blast_id='BLAST_TEST_ID',
            method=defs.TimeoutMethod.ITERATE_BLAST,
        ), LOOP_ITERATION_DELAY)

    # def _load_global_feature_flags(self):
    #     persistents_data = self.persistents_table.get_first(name=GLOBAL_FEATURE_FLAGS_PERSISTENT_NAME)
    #     if persistents_data is None:
    #         persistents_data = {}
    #     new_values = self.global_feature_flags.load_values(persistents_data)
    #     new_values[PersistentFields.name] = GLOBAL_FEATURE_FLAGS_PERSISTENT_NAME
    #     self.persistents_table.put(new_values)

    def call_timeout_with_params(self, params: dict, timeout_seconds: int):
        remaining_timeout = None
        if timeout_seconds > defs.MAX_TIMEOUT_SECONDS:
            remaining_timeout = timeout_seconds - defs.MAX_TIMEOUT_SECONDS
            timeout_seconds = defs.MAX_TIMEOUT_SECONDS
            params['remaining_timeout_seconds'] = remaining_timeout

        # spellchecker: disable
        step_function_input = {
            "WAIT_TIME": timeout_seconds,
            "body": {},
            "method": "POST",
            "principalId": "",
            "stage": "dev",
            "headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "Accept-Language": "en-us",
                "CloudFront-Forwarded-Proto": "https",
                "CloudFront-Is-Desktop-Viewer": "true",
                "CloudFront-Is-Mobile-Viewer": "false",
                "CloudFront-Is-SmartTV-Viewer": "false",
                "CloudFront-Is-Tablet-Viewer": "false",
                "CloudFront-Viewer-Country": "US",
                "Cookie": "__gads=ID=d51d609e5753330d:T=1443694116:S=ALNI_MbjWKzLwdEpWZ5wR5WXRI2dtjIpHw; __qca=P0-179798513-1443694132017; _ga=GA1.2.344061584.1441769647",
                "Host": "xxx.execute-api.us-east-1.amazonaws.com",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/601.6.17 (KHTML, like Gecko) Version/9.1.1 Safari/601.6.17",
                "Via": "1.1 c8a5bb0e20655459eaam174e5c41443b.cloudfront.net (CloudFront)",
                "X-Amz-Cf-Id": "z7Ds7oXaY8hgUn7lcedZjoIoxyvnzF6ycVzBdQmhn3QnOPEjJz4BrQ==",
                "X-Forwarded-For": "221.24.103.21, 54.242.148.216",
                "X-Forwarded-Port": "443",
                "X-Forwarded-Proto": "https"
            },
            "query": {},
            "path": {},
            "requestPath": "",
            "identity": {
                "cognitoIdentityPoolId": "",
                "accountId": "",
                "cognitoIdentityId": "",
                "caller": "",
                "apiKey": "",
                "sourceIp": "221.24.103.21",
                "cognitoAuthenticationType": "",
                "cognitoAuthenticationProvider": "",
                "userArn": "",
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/601.6.17 (KHTML, like Gecko) Version/9.1.1 Safari/601.6.17",
                "user": ""
            },
            "stageVariables": {}
        }
        # spellchecker: enable
        step_function_input["requestPath"] = f"/timeout/{serialize(params)}"

        name = str(uuid.uuid4())

        client = boto3.client('stepfunctions')
        client.start_execution(
            stateMachineArn=self.env.TIMEOUT_STEP_FUNC_ARN,
            name=name,
            input=json.dumps(step_function_input),
            traceHeader=name
        )
