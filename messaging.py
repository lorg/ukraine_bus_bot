import copy
import asyncio
import logging
from dataclasses import dataclass, asdict
from typing import List, Optional

import requests  # type: ignore
import aiohttp
from twilio.rest import Client as TwilioClient  # type: ignore

import utils
from environment import Environment

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

WASSENGER_NUMBER_EXISTS_URL = 'https://api.wassenger.com/v1/numbers/exists'
WASSENGER_MESSAGES_URL = "https://api.wassenger.com/v1/messages"
WASSENGER_GROUP_URL = 'https://api.wassenger.com/v1/devices/{device_id}/groups'
WASSENGER_GET_GROUP_URL = 'https://api.wassenger.com/v1/devices/{device_id}/groups/{group_id}'
WASSENGER_ADD_GROUP_PARTICIPANTS_URL = 'https://api.wassenger.com/v1/devices/{device_id}/groups/{group_id}/participants'
PRODUCTION_ENV_NAME = 'production'

TWILIO_MESSAGE_MAX_LEN = 1600
WASSENGER_MESSAGE_MAX_LEN = 6000
MAX_WHATSAPP_GROUP_NAME_LEN = 25

MAX_WHATSAPP_GROUP_RETRIES = 10


@dataclass
class Message:
    device: str
    phone: Optional[str]
    message: str
    group: Optional[str] = None


class MessagingSession:
    def __init__(self, queue_messages: bool = True, environment: Environment = Environment()):
        self.env: Environment = environment
        self.messages: List[Message] = []
        self.queue_messages: bool = queue_messages
        self.sent_messages: List[Message] = []

    def _send_message(self, message: Message, is_admin_message: bool = False):
        raise NotImplementedError

    def _flush_messages(self):
        raise NotImplementedError

    def flush_messages(self):
        self._flush_messages()
        self.sent_messages += self.messages
        self.messages = []

    def notify_admins(self, message: str):
        for admin_phone in self.env.ADMIN_NUMBERS:
            self.send_message(admin_phone, message, is_admin_message=True)

    def send_message(self, phone: str, message: str, is_admin_message: bool = False):
        if is_admin_message:
            if self.env.ENV_NAME == PRODUCTION_ENV_NAME:
                message = f"*PRODUCTION:* {message}"
            else:
                message = f"*DEV:* {message}"
            source_device = self.env.ADMIN_MESSAGES_SOURCE_DEVICE
        else:
            source_device = self.env.SOURCE_DEVICE

        message_obj = Message(
            device=source_device,
            phone=phone,
            message=message,
        )
        if self.queue_messages:
            self.messages.append(message_obj)
        else:
            self._send_message(message_obj, is_admin_message)
            self.sent_messages.append(message_obj)

    def clear_sent_messages(self):
        self.sent_messages = []


class TwilioSession(MessagingSession):
    def _flush_messages(self):
        twilio_client = TwilioClient(
            self.env.TWILIO_ACCOUNT_SID, self.env.TWILIO_AUTH_TOKEN)
        for message in self.messages:
            source_number = utils.choose_source_number(self.env.SMS_SOURCE_NUMBERS.split(','), message.phone)
            for message_text in utils.split_message_by_max_len(message.message, TWILIO_MESSAGE_MAX_LEN):
                twilio_client.messages.create(
                    from_=source_number,
                    body=message_text,
                    to=f'{message.phone}'
                )

    def _send_message(self, message: Message, is_admin_message: bool = False):
        assert message.phone
        twilio_client = TwilioClient(
            self.env.TWILIO_ACCOUNT_SID, self.env.TWILIO_AUTH_TOKEN)

        if is_admin_message:
            source_number = self.env.OTHER_NUMBER
        else:
            source_number = utils.choose_source_number(self.env.SMS_SOURCE_NUMBERS.split(','), message.phone)

        for message_text in utils.split_message_by_max_len(message.message, TWILIO_MESSAGE_MAX_LEN):
            twilio_client.messages.create(
                from_=source_number,
                body=message_text,
                to=f'{message.phone}'
            )


class WassengerSession(MessagingSession):
    def __init__(self, queue_messages: bool = True, environment=Environment()):
        super().__init__(queue_messages, environment)
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Token": self.env.WASSENGER_API_KEY
        })

    # Should not be called more than 60 times per minute !
    def is_phone_number_exists(self, phone: str):
        try:
            response = self.session.post(url=WASSENGER_NUMBER_EXISTS_URL, json={ 'phone': phone })
            if response.status_code != 200 and response.status_code != 201:
                logger.info("status code: %s, response content: %s", response.status_code, response.content)
                return False

            return True
        except Exception as exc:
            logger.exception(
                "Unable to check phone number %s",
                phone,
                str(exc.__class__))
            return False

    def send_group_message(self, group: str, message: str):
        source_device = self.env.SOURCE_DEVICE
        message_obj = Message(
            device=source_device,
            phone=None,
            message=message,
            group=group
        )
        if self.queue_messages:
            self.messages.append(message_obj)
        else:
            self._send_message(message_obj, is_admin_message=False)
            self.sent_messages.append(message_obj)

    def _send_message(self, message: Message, is_admin_message: bool = False):
        assert message.phone or message.group

        for message_text in utils.split_message_by_max_len(message.message, WASSENGER_MESSAGE_MAX_LEN):
            payload = asdict(message)
            payload['message'] = message_text
            if not message.group:
                del payload['group']
            if not message.phone:
                del payload['phone']
            if self.queue_messages:
                asyncio.run(self._async_post(payload, self.session))
            else:
                self._post(payload, self.session)

    def _post(self, payload, session: requests.Session):
        # pylint: disable=W0703
        try:
            response = session.post(url=WASSENGER_MESSAGES_URL, json=payload)
            if response.status_code != 200 and response.status_code != 201:
                logger.info("status code: %s, response content: %s", response.status_code, response.content)
        except Exception as exc:
            logger.exception(
                "Unable to send message '%s' to %s due to %s",
                payload['message'],
                payload['phone'],
                str(exc.__class__))

    async def _async_post(self, payload, session):
        # pylint: disable=W0703
        try:
            async with session.post(url=WASSENGER_MESSAGES_URL, json=payload) as response:
                if response.status != 200 and response.status != 201:
                    logger.info("status code: %s, response content: %s", response.status, await response.content.read())
        except Exception as exc:
            logger.exception(
                "Unable to send message '%s' to %s due to %s",
                payload['message'],
                payload['phone'],
                str(exc.__class__))

    async def _async_flush_messages(self):
        async with aiohttp.ClientSession() as session:
            session.headers.update({
                "Content-Type": "application/json",
                "Token": self.env.WASSENGER_API_KEY
            })
            payloads_to_send = []
            for message in self.messages:
                for text in utils.split_message_by_max_len(message.message, WASSENGER_MESSAGE_MAX_LEN):
                    new_message = copy.copy(message)
                    new_message.message = text
                    payload = asdict(new_message)
                    if not new_message.group:
                        del payload['group']
                    if not new_message.phone:
                        del payload['phone']
                    payloads_to_send.append(payload)
            await asyncio.gather(*[self._async_post(payload, session) for payload in payloads_to_send])
            self.sent_messages += self.messages
            self.messages = []

    def _flush_messages(self):
        if self.messages:
            asyncio.run(self._async_flush_messages())

    def create_whatsapp_group(self, group_name: str, regular_participants: List[str], admin_participants: List[str], description: str) -> Optional[str]:
        """Returns the whatsapp group ID if the group was created successfully otherwise None"""
        regular_participants_set = set(regular_participants)
        admin_participants_set = set(admin_participants)
        regular_participants_set -= admin_participants_set
        regular_participants = list(regular_participants_set)
        admin_participants = list(admin_participants_set)
        success = False
        for retry in range(MAX_WHATSAPP_GROUP_RETRIES):
            params = dict(
                name=group_name[:MAX_WHATSAPP_GROUP_NAME_LEN] if retry == 0 else group_name[:MAX_WHATSAPP_GROUP_NAME_LEN - 2] + ' ' + str(retry),
                participants=[dict(phone=p, admin=False) for p in regular_participants] + [dict(phone=p, admin=True) for p in admin_participants],
                description=description,
            )
            response = self.session.post(WASSENGER_GROUP_URL.format(device_id=self.env.SOURCE_DEVICE), json=params)
            if response.status_code == 409:
                logger.warning("Unable to create group %s, status: %s, body: %s", group_name, response.status_code, repr(response.content))
                continue
            if response.status_code != 200 and response.status_code != 201:
                logger.error("Unable to create group %s, status: %s, body: %s", group_name, response.status_code, repr(response.content))
                return None
            success = True
            break
        if not success:
            return None
        logger.info(
            "Created group %s with %s regular participants and %s admin participants, response code: %s, response: %s",
            group_name,
            len(regular_participants),
            len(admin_participants),
            response.status_code,
            response.content)
        return response.json()['id']

    def get_whatsapp_group(self, whatsapp_group_id: str) -> Optional[dict]:
        """Returns the whatsapp group if the group was created successfully otherwise None"""
        response = self.session.get(WASSENGER_GET_GROUP_URL.format(device_id=self.env.SOURCE_DEVICE, group_id=whatsapp_group_id))
        if response.status_code != 200 and response.status_code != 201:
            logger.error("Unable to get group %s, status: %s, body: %s", whatsapp_group_id, response.status_code, repr(response.content))
            return None

        logger.info(
            "Got group %s. Group data: %s",
            whatsapp_group_id,
            response.content)
        return response.json()

    def add_whatsapp_group_participant(self, whatsapp_group_id: str, phone: str, is_admin: bool):
        """Add a participant to a whatsapp group"""
        params = dict(participants=[dict(phone=phone, admin=is_admin)])
        logger.info('Trying to add participant %s to group %s', str(params), whatsapp_group_id)
        url = WASSENGER_ADD_GROUP_PARTICIPANTS_URL.format(device_id=self.env.SOURCE_DEVICE, group_id=whatsapp_group_id)
        response = self.session.post(url, json=params)
        if response.status_code != 200 and response.status_code != 201:
            logger.warning("Unable to add participant %s to group %s, status: %s, body: %s", phone, whatsapp_group_id, response.status_code, repr(response.content))
            return

        logger.info("%s was added  to group %s", phone, whatsapp_group_id)


class MockMessagingSession(MessagingSession):

    def print_messages(self):
        for message in self.sent_messages:
            print(f'"{message.message}" -> {message.phone}\n\n')

    def _send_message(self, message: Message, is_admin_message: bool = False):
        pass

    def _flush_messages(self):
        pass


class MockWassengerSession(WassengerSession):

    def __init__(self, queue_messages: bool = True, environment=Environment()):
        super().__init__(queue_messages, environment)
        self.next_group_id = 0

    def is_phone_number_exists(self, phone: str):
        return phone.startswith('+')

    def print_messages(self):
        for message in self.sent_messages:
            print(f'"{message.message}" -> {message.phone}\n\n')

    def create_whatsapp_group(self, group_name: str, regular_participants: List[str], admin_participants: List[str], description: str) -> Optional[str]:
        result = "whatsapp_group_" + str(self.next_group_id)
        self.next_group_id += 1
        return result

    def get_whatsapp_group(self, whatsapp_group_id: str) -> Optional[dict]:
        result = dict(device="device", name="group-name", participants=[])
        return result

    def add_whatsapp_group_participant(self, whatsapp_group_id: str, phone: str, is_admin: bool):
        pass

    def _send_message(self, message: Message, is_admin_message: bool = False):
        pass

    def _flush_messages(self):
        pass
