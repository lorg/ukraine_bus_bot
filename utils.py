import io
import os
import re
import uuid
import json
import base64
import urllib
import pstats
import string
import logging
import cProfile
import datetime
import collections
from random import randint
from enum import Enum
from functools import wraps
from itertools import islice
from decimal import Decimal
from typing import Callable, Iterable, List, Any, Optional, TypeVar, Union, Sequence, Type, Dict

from flask import jsonify  # type: ignore
try:
    import sentry_sdk
except ImportError:
    class sentry_sdk:
        @staticmethod
        def init(dsn: str, **kwargs):
            pass

        @staticmethod
        def flush():
            pass


from environment import Environment

RUN_PROFILER = int(os.environ.get('RUN_PROFILER', 0))
DEFAULT_SHORTENED_INVITE_PATH = '{base_url}h/{host_slug}'
SLUGED_SHORTENED_INVITE_PATH = '{base_url}h/{host_slug}/{invite_slug}'

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FALSE_STRINGS = ["0", "", "false"]


def decode_json(data) -> Any:
    """unwrap json from a data used in forms"""
    return json.loads(data.decode('utf-8'))


def deserialize(param) -> Any:
    """unwrap base64 and json from a param used in forms"""
    return json.loads(base64.b64decode(param.encode('utf8')).decode('utf8'))


def serialize(param: dict) -> str:
    """wrap a dict in json and base64 to use as a paramater in forms"""
    return base64.b64encode(json.dumps(param).encode('utf8')).decode('utf8')


def none_if_blank(param) -> Optional[str]:
    """returns a stripped string or None if string it empty"""
    if param:
        param = param.strip()
        if param:
            return param

    return None


def is_number(some_str) -> bool:
    return all(x in "0123456789" for x in some_str)


def plural(num: int) -> str:
    if num == 1:
        return ''
    return 's'


T = TypeVar('T')


def find(seq: Iterable[T], key_func: Callable[[T], bool]) -> Optional[T]:
    for element in seq:
        if key_func(element):
            return element
    return None


def argfind(seq: Iterable[T], key_func: Callable[[T], bool]) -> Optional[int]:
    """Return the index of the first element x in seq for which key_func(x) is truthy, None if not found"""
    for idx, element in enumerate(seq):
        if key_func(element):
            return idx
    return None


def catch_exceptions_flask(func):
    # pylint: disable=W0703
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            logger.info("%s called", str(func))
            return func(*args, **kwargs)
        except Exception as exc:
            logger.exception("error in calling %s", str(func))
            sentry_sdk.flush()
            return jsonify({"error": "had an error"})
    return wrapper


def catch_exceptions(func):
    # pylint: disable=W0703
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            logger.info("%s called", str(func))
            return func(*args, **kwargs)
        except Exception as exc:
            logger.exception("error in calling %s", str(func))
            sentry_sdk.flush()
            return
    return wrapper


HEBREW_CHARS = "אבגדהוזחטיכלמנסעפצקרשתךףץםן"


def quote_plus_hebrew(text):
    return ''.join(c if c in HEBREW_CHARS else urllib.parse.quote_plus(c) for c in text)


def quote_hebrew(text):
    return ''.join(c if c in HEBREW_CHARS else urllib.parse.quote(c) for c in text)


def create_shortened_link(env: Environment, host_slug: str, invite_slug: str = None) -> str:
    if not invite_slug:
        return DEFAULT_SHORTENED_INVITE_PATH.format(base_url=env.SHORTENER_URL, host_slug=host_slug)
    else:
        return SLUGED_SHORTENED_INVITE_PATH.format(base_url=env.SHORTENER_URL, host_slug=host_slug, invite_slug=invite_slug)


def create_sms_link(phone: str, message: str = None) -> str:
    if message:
        return f"sms:{phone}&body={quote_hebrew(message)}"
    return f"sms:{phone}"


def create_whatsapp_link(phone: str, message: str = None) -> str:
    phone = remove_prefix(phone, "+")
    if message:
        return f"https://api.whatsapp.com/send/?phone={phone}&text={quote_plus_hebrew(message)}"
    return f"https://api.whatsapp.com/send/?phone={phone}"

    # if message:
    #    return f"https://wa.me/{phone}?text={quote_plus_hebrew(message)}"
    # return f"https://wa.me/{phone}"


def get_short_uid() -> str:
    my_uuid = str(uuid.uuid4())
    return my_uuid[:6]


def get_random(length: int) -> str:
    my_uuid = str(uuid.uuid4())
    return my_uuid[:length]


def get_rundom_number(length: int):
    # length - the number of decimal digits
    range_start = 10**(length - 1)
    range_end = (10**length) - 1
    return randint(range_start, range_end)


def get_uid() -> str:
    my_uuid = str(uuid.uuid4())
    return my_uuid


def with_profiler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not RUN_PROFILER:
            return func(*args, **kwargs)
        prof = cProfile.Profile()
        retval = prof.runcall(func, *args, **kwargs)
        buff = io.StringIO()
        pstats.Stats(
            prof, stream=buff
        ).sort_stats('cumtime').print_stats(100)
        logger.info("Profile results for %s:\n%s",
                    func.__name__, buff.getvalue())
        return retval

    return wrapper


def registry(field_class, add_name=False):
    def wrap(cls):
        if hasattr(cls, 'start_wrap'):
            cls.start_wrap()
        cls.objects = []
        for key, value in cls.__dict__.items():
            if key.startswith('_'):
                continue
            if not isinstance(value, field_class):
                continue
            if add_name:
                value.name = key
            if hasattr(cls, 'add_object'):
                cls.add_object(value)
            cls.objects.append(value)
        return cls
    return wrap


def remove_prefix(s: str, prefix: str) -> str:
    if s.startswith(prefix):
        return s[len(prefix):]
    return s


def replace_prefix(s: str, prefix: str, new_prefix: str) -> str:
    if s.startswith(prefix):
        s = new_prefix + s[len(prefix):]
    return s


def is_israeli_phone(phone: str) -> bool:
    return phone.startswith('+972')


def is_local_israeli_phone(phone: str) -> bool:
    return phone.startswith('0') and all(c in string.digits for c in phone)


def make_israeli_phone_local(phone: str) -> str:
    return replace_prefix(phone, '+972', '0')


def make_israeli_phone_international(phone: str) -> str:
    return replace_prefix(phone, '0', '+972')


def start_sentry():
    env = Environment()
    if not env.SENTRY_DSN:
        logger.info(
            "No SENTRY_DSN environment variable, Sentry is not configured")
        return
    # pylint: disable=abstract-class-instantiated
    sentry_sdk.init(
        dsn=env.SENTRY_DSN,
        #integrations=[FlaskIntegration(), AwsLambdaIntegration()],

        environment=env.ENV_NAME,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0
    )


def start_rookout(env: Environment):
    # pylint: disable=C0415
    if not env.ROOKOUT_TOKEN:
        return
    if not env.RUN_ROOKOUT:
        return
    try:
        import rook  # type: ignore
    except ImportError:
        rook = None
    if rook:
        rook.start(token=env.ROOKOUT_TOKEN, labels={"env": env.ENV_NAME})


def percentile_averages(numbers: Sequence[Union[int, float]]) -> List[Optional[float]]:
    numbers = sorted(numbers)
    result: List[Optional[float]] = []
    average: Optional[float]
    len_numbers = len(numbers)
    for i in range(10):
        percentile_numbers = numbers[int(
            0.1 * i * len_numbers):int(0.1 * (i + 1) * len_numbers)]
        if len(percentile_numbers):
            average = float(sum(percentile_numbers)) / len(percentile_numbers)
        else:
            average = None
        result.append(average)
    return result


def groupby(seq, key=None):
    if key is None:
        def key(param):
            return param
    result = collections.defaultdict(list)
    for item in seq:
        result[key(item)].append(item)
    return result


def pretty_minutes(seconds: int) -> str:
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02}:{seconds:02}"


def chunks(seq, size):
    # Taken from: https://stackoverflow.com/a/22045226/163536
    seq = iter(seq)
    return iter(lambda: tuple(islice(seq, size)), ())


def flatten_dicts(data: Any):
    if not isinstance(data, dict):
        return data

    result = {}
    for key, value in data.items():
        value = flatten_dicts(value)
        if not isinstance(value, dict):
            result[key] = value
            continue
        for sub_key, sub_value in value.items():
            result[f"{key}__{sub_key}"] = sub_value
    return result


def parse_duration_to_seconds(duration_str: str) -> Optional[int]:
    duration_re = r"^((?P<minutes>\d+)m)|((?P<hours>\d+)h)$"
    match = re.match(duration_re, duration_str)
    if not match:
        return None
    groups = match.groupdict()
    hours = groups['hours']
    minutes = groups['minutes']
    if minutes:
        return int(minutes) * 60
    if hours:
        return int(hours) * 3600
    return None


def get_optional_datetime(dynamodb_record: dict, field_name: str) -> Optional[datetime.datetime]:
    timestamp = dynamodb_record.get(field_name)
    if timestamp is None:
        return None
    return datetime.datetime.fromisoformat(timestamp)


def get_datetime(dynamodb_record: dict, field_name: str) -> datetime.datetime:
    timestamp = dynamodb_record[field_name]
    return datetime.datetime.fromisoformat(timestamp)


def is_phone(s: str) -> bool:
    if not s:
        return False
    if s.startswith('+') and all(c in string.digits for c in s[1:]):
        return True
    return False


def get_enum_value(d: dict, field_name: str, default: Enum) -> Enum:
    value = d.get(field_name)
    if not value:
        return default
    return default.__class__(value)


def get_optional_enum_value(d: dict, field_name: str, enum: Type[Enum]) -> Optional[Enum]:
    value = d.get(field_name)
    if not value:
        return None
    return enum(value)


class DecimalJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return json.JSONEncoder.default(self, o)


def unflatten_dict(d: Dict[str, Any]) -> dict:
    """{'a[b][c]': 'v'} -> {'a': {'b': {'c': 'v'}}}"""
    result = {}
    for k, v in d.items():

        if not k.endswith(']'):
            result[k] = v
            continue

        base_key = k[:k.find('[')]
        rest_keys = k[k.find('[') + 1:-1].split('][')
        cur_keys = [base_key] + rest_keys
        cur_dict = result
        for k2 in cur_keys[:-1]:
            if k2 not in cur_dict:
                cur_dict[k2] = {}
            cur_dict = cur_dict[k2]
        cur_dict[cur_keys[-1]] = v

    return result


def remove_dup_spaces(s: str) -> str:
    result = re.subn(" +", ' ', s)
    return result[0]


def clean_for_json(d: Any):
    if isinstance(d, dict):
        return {k: clean_for_json(v) for k, v in d.items()}
    if isinstance(d, list):
        return [clean_for_json(x) for x in d]
    if isinstance(d, Decimal):
        return float(d)
    if isinstance(d, (int, str, float)):
        return d
    return str(d)


def clean_phone(phone):
    phone = phone.replace('-', '').replace(' ', '')
    if phone.startswith('05'):
        return '+972' + phone[1:]
    if phone.startswith('5'):
        return '+972' + phone
    if phone.startswith('972'):
        return '+' + phone
    return phone


def clean_phone_for_missed_call_handler(phone):
    if phone.startswith('+5') and len(phone) == 10:
        return '+972' + phone[1:]
    if phone.startswith('97200'):
        return '+' + remove_prefix(phone, '97200')
    return phone


def choose_source_number(source_numbers: List[str], target_number: str) -> str:
    longest_prefixes = [(idx, os.path.commonprefix([number, target_number])) for idx, number in enumerate(source_numbers)]
    return source_numbers[max(longest_prefixes, key=lambda idx_prefix: len(idx_prefix[1]))[0]]


def split_message_by_max_len(message: str, max_len: int, split_by: Optional[str] = '\n') -> List[str]:

    if split_by is None:
        lines = list(message)
    else:
        lines = message.split(split_by)
    result_messages: List[str] = []
    for line in lines:
        if (not result_messages) or (result_messages[-1] and len(result_messages[-1].encode('utf8')) + len(line.encode('utf8')) + 1 >= max_len):
            if len(line.encode('utf8')) > max_len:
                if split_by == '\n':
                    result_messages.extend(split_message_by_max_len(line, max_len, ' '))
                else:
                    result_messages.extend(split_message_by_max_len(line, max_len, None))
            else:
                result_messages.append(line)
        else:
            if split_by == '\n':
                result_messages[-1] += '\n' + line
            elif split_by == ' ':
                result_messages[-1] += ' ' + line
            else:
                result_messages[-1] += line
    return result_messages
