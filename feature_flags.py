import copy
import enum
from typing import Any, Type, Dict
import dataclasses
from dataclasses import dataclass

import utils

DEFAULT_SUBSCRIBER_ITERATION_INTERVAL_SEC = '30'


class DynamicLinkType(enum.Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    PROFILE = "profile"
    COMMUNITY = "community"
    CUSTOM = "custom"


@dataclass
class Flag:
    name: str = dataclasses.field(init=False)
    default_value: Any
    value_type: Type
    description: str = ""
    value: Any = dataclasses.field(init=False)

    def convert_flag_value(self, value):
        if value is None:
            return self.default_value
        if self.value_type == int:
            if isinstance(value, str):
                value = int(value)
        if self.value_type == bool:
            if isinstance(value, str):
                if value.lower() in utils.FALSE_STRINGS:
                    value = False
                else:
                    value = True
        return value

    def get_flag_value(self, flag_holder: Dict) -> Any:
        if hasattr(self, 'value'):
            return self.value
        value = flag_holder.get(self.name, self.default_value)
        return self.convert_flag_value(value)


class BaseFeatureFlags:
    def __init__(self):
        self.all_flags: Dict[str, Flag] = {}
        for key, value in list(self.__class__.__dict__.items()):
            if not isinstance(value, Flag):
                continue
            value.name = key
            new_value = copy.copy(value)
            self.all_flags[key] = new_value
            setattr(self, key, new_value)


class GlobalFeatureFlags(BaseFeatureFlags):

    def load_values(self, data: Dict) -> Dict:
        result = {}
        for key, flag in self.all_flags.items():
            flag_value = flag.get_flag_value(data)
            result[key] = flag_value
            flag.value = flag_value
        return result

    test_feature_flag = Flag(
        True,
        bool,
        "a test feature flag",
    )
