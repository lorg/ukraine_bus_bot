import re
import enum
import copy
import inspect
import logging
import dataclasses
from enum import Enum
from dataclasses import asdict, dataclass
from typing import Optional, Dict, Type, TypeVar, Generic, List

import jinja2

import db
import utils
import environment

env = environment.Environment()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_LANGUAGE_CODE = 'en_US'


class TemplateLang(enum.Enum):
    JINJA = 'jinja'


@dataclass
class Text:
    name: str = dataclasses.field(init=False, default='')
    text: str
    description: str = ""
    context: Optional[dict] = None
    template_lang: Optional[str] = None

    def __post_init__(self):
        self.jinja_env: Optional[jinja2.Environment] = None

    def update_format(self, context: Optional[dict] = None, **kwargs) -> "Text":
        if context is not None:
            kwargs.update(context)
        new_text = copy.copy(self)
        new_text.text = new_text.format(**kwargs)
        if new_text.context is None:
            new_text.context = {}
        new_text.context.update(kwargs)
        return new_text

    def format(self, context: Optional[dict] = None, **kwargs) -> str:
        if self.template_lang == TemplateLang.JINJA.value:
            if self.name is None or self.jinja_env is None:
                raise Exception("missing jinja env or name")
            template = self.jinja_env.get_template(self.name)
            return template.render(**kwargs)
        if context is not None:
            kwargs.update(context)
        return self.text.format(**kwargs)


class Param:
    def __init__(self, param_type: str, regexp: str):
        self.param_type = param_type
        self.min_repeats = 1
        self.max_repeats = 1
        self.regexp_pattern: str = regexp

    @classmethod
    def phone(cls) -> 'Param':
        return cls('phone', r'(?P<v>[+](\d+))')

    @classmethod
    def number(cls) -> 'Param':
        return cls('number', r'(?P<v>\d+)')

    @classmethod
    def string(cls) -> 'Param':
        return cls('string', '(?P<v>.+)')

    @classmethod
    def const(cls, value) -> 'Param':
        return cls('const', f"(?P<v>{re.escape(value)})")

    @classmethod
    def regexp(cls, pattern):
        compiled = re.compile(pattern)
        if 'v' not in compiled.groups:
            pattern = f"(?P<v>{pattern})"
        return cls('regexp', pattern)

    @classmethod
    def optional(cls, param: 'Param'):
        new_param_spec = Param(param.param_type, param.regexp_pattern)
        new_param_spec.max_repeats = param.max_repeats
        new_param_spec.min_repeats = 0
        return new_param_spec

    @classmethod
    def sequence(cls, param: 'Param', *, min_repeats=1, max_repeats=None):
        new_param_spec = Param(param.param_type, param.regexp_pattern)
        new_param_spec.max_repeats = max_repeats
        new_param_spec.min_repeats = min_repeats
        return new_param_spec


class ParseErrorCode(Enum):
    MISSING_SINGLE_PARAM = 'missing param'
    MISSING_MULTI_PARAM = 'missing multi param'
    INCORRECT_FORMAT = 'incorrect format'


@dataclass
class ParseError:
    param_name: Optional[str]
    error_code: ParseErrorCode


@dataclass
class ParseResult:
    errors: List[ParseError]
    success: bool
    values: Dict[str, List[str]]


@dataclass
class UserInput(Text):
    param_specs: Optional[Dict[str, Param]] = None

    def __post_init__(self):
        options = set(self.text.split(','))
        new_options = set()
        for option in options:
            new_options.add(option.replace('-', ' '))
        self._options = options | new_options

    @property
    def options(self):
        return self._options

    def __contains__(self, item):
        return item in self.options

    def parse_params(self, params: str):
        assert self.param_specs
        result = ParseResult([], True, {})
        remaining_params = params.split()
        for param_name, param_spec in self.param_specs.items():
            matches: List[Optional[re.Match]] = [re.match(param_spec.regexp_pattern, remaining_param) for remaining_param in remaining_params[:param_spec.max_repeats]]
            first_none_idx = utils.argfind(matches, lambda m: m is None)
            if first_none_idx is not None:
                matches = matches[:first_none_idx]
            if param_spec.min_repeats > len(matches):
                if remaining_params:
                    result.errors.append(ParseError(param_name, ParseErrorCode.INCORRECT_FORMAT))
                elif matches == 0:
                    result.errors.append(ParseError(param_name, ParseErrorCode.MISSING_SINGLE_PARAM))
                else:
                    result.errors.append(ParseError(param_name, ParseErrorCode.MISSING_MULTI_PARAM))
                result.success = False
                return result
            result.values[param_name] = [m.groupdict()['v'] for m in matches if m is not None]
            remaining_params = remaining_params[len(matches):]
        return result


@dataclass
class MailTemplate(Text):
    body_html: str = ""
    body_text: str = ""

    def update_format(self, context: Optional[dict] = None, **kwargs) -> "Text":
        if context is not None:
            kwargs.update(context)
        new_text = copy.copy(self)
        new_text.body_text = new_text.body_text.format(**kwargs)
        new_text.body_html = new_text.body_html.format(**kwargs)
        new_text.context = kwargs

        return new_text


@dataclass
class WebText(Text):
    page: str = ""


@dataclass
class AppText(Text):
    version: str = ""


T = TypeVar('T', bound=Text)  # pylint: disable=invalid-name


class Texts(Generic[T]):
    text_class: Type[T]
    text_type = ''
    all_texts: Dict[str, T] = {}

    def __init__(self, lang_code, table_class=db.DynamoDBTable):
        self.texts_table: db.DynamoDBTable = table_class(
            env.TEXTS_TABLE, 'lang_code', 'type_name')
        self.lang_code = lang_code
        self.all_texts = {}
        all_texts = self.all_texts
        self.jinja_loader = jinja2.FunctionLoader(lambda name: all_texts[name].text)
        self.jijna_env = jinja2.Environment(loader=self.jinja_loader, autoescape=False)
        for key, value in inspect.getmembers(self):
            if not isinstance(value, self.text_class):
                continue
            value.name = key
            new_value = copy.copy(value)
            self.all_texts[key] = new_value
            setattr(self, key, new_value)
            new_value.jinja_env = self.jijna_env

    def _load_from_texts(self, db_items: List[dict]) -> set:
        """Load texts data from the provided list of texts,
        return the set of text names that were loaded"""
        db_names = set()
        for item in db_items:
            type_, name = item['type_name'].split('.')
            if self.text_type and type_ != self.text_type:
                continue
            original_item = getattr(self, name, None)
            item['text'] = item['text'].replace('\\n', '\n')
            new_text = self.text_class(item['text'], item['description'])
            if type_ == 'mail_templete':
                new_text.body_text = item['body_text']  # type: ignore
                new_text.body_html = item['body_html']  # type: ignore
            if type_ == 'web_text':
                new_text.page = item['page']  # type: ignore
            if type_ == 'input' and original_item:
                new_text.param_specs = original_item.param_specs  # type: ignore
            new_text.template_lang = item.get('template_lang')
            new_text.name = name
            self.all_texts[name] = new_text
            new_text.jinja_env = self.jijna_env
            setattr(self, name, new_text)
            db_names.add(name)
        return db_names

    def add_override_texts(self, override_texts: List[dict]):
        self._load_from_texts(override_texts)

    def load_db(self):
        items = self.texts_table.query(lang_code=self.lang_code)

        original_names = {name for name in self.all_texts}

        db_names = self._load_from_texts(items)

        for text_name in original_names - db_names:
            text = self.all_texts[text_name]
            item = asdict(text)
            item['lang_code'] = self.lang_code
            item['type_name'] = f"{self.text_type}.{item['name']}"
            if 'param_specs' in item:
                del item['param_specs']
            self.texts_table.put(item)


class WebPages:
    # pylint: disable=R0903
    PROFILE = "profile"
    SIGNUP = "signup"
    HOST_GALLERY = "hosts"
    WEB_SIGNUP = "web_signup"
    WEB_SIGNUP_THANK_YOU = "web_signup_thank_you"
    WEB_SUBSCRIBE = "web_subscribe"
    WEB_SUBSCRIBE_THANK_YOU = "web_subscribe_thank_you"


class AppTypes:
    WAITLIST = "waitlist"
