# pylint: disable=too-many-lines

from typing import Dict


import utils
from texts_infra import UserInput, Texts, Text, MailTemplate, WebText, WebPages, Param, TemplateLang, AppText


class SpecialInputTexts:
    # pylint: disable=R0903
    RMRF = "rm -rf"
    DROP_TABLE = "drop table"


@utils.registry(UserInput, add_name=True)
class Inputs(Texts[UserInput]):
    text_class = UserInput
    text_type = 'input'
    all_texts: Dict[str, UserInput] = {}

    clear = UserInput(
        "clear", "Sends a long empty message to clear the screen")
    ping = UserInput(
        "ping", "Sends a ping message to the bot")
    yes = UserInput(
        "yes,sure,ok", "when someone sends yes")


class Prompts(Texts[Text]):
    text_class = Text
    text_type = "prompt"

    pong = Text("pong", "response to 'ping'")
