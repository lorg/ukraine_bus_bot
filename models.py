import uuid
import logging
import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, List
from decimal import Decimal
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

import db
from db import CreationTimestampField
import utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# The following small hack allows us to get autocomplete in VSCode for pydantic classes by pretending they are dataclasses
# when type checking only.
if TYPE_CHECKING:  # pragma: no cover
    static_check_init_args = dataclass
    Field = field  # type: ignore
else:
    def static_check_init_args(cls):
        return cls


class MessagingMethod(Enum):
    WHATSAPP = 'whatsapp'
    SMS = 'sms'
