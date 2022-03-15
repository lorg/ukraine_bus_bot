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


class BlastStatus(Enum):
    IN_PROGRESS = 'in progress'
    ERROR = 'error'
    DONE = 'done'


class Blast(BaseModel):
    blast_id: str
    status: BlastStatus
    started_timestamp: str
    ended_timestamp: str
    num_phones: str
    last_phone_sent: str

class BlastPhone(BaseModel):
    blast_id: str
    phone: str
    phone_idx: str
