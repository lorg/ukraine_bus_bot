import requests

import environment

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GoogleSheets:
    def __init__(self, env: environment.Environment):
        self.env = env

    def report_log(self, from_phone: str, to_phone: str, message_text: str, status_code: str, status_text: str):
        form_data = {
            "entry.1960653426": from_phone,  # From phone number
            "entry.605564864": to_phone,  # To phone number
            "entry.200012088": message_text,  # Message text
            "entry.951760456": status_code,  # Status code
            "entry.493852667": status_text,  # Status text
            "fvv": 1,
            # "draftResponse":'[]',
            "pageHistory": 0,
            "fbzx": 7339899578519504554
        }

        url = self.env.GOOGLE_SHEETS_LOG_URL
        response = requests.post(url, data=form_data)
        logger.info(f"Google sheets log response: {response.status_code}")
