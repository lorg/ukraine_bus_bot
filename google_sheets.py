import requests
import logging
import json

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account


import environment

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


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

    def read_sheet(self) -> list:
        spreadsheet_id = self.env.GOOGLE_SHEET_ID
        spreadsheet_range = self.env.GOOGLE_SHEET_RANGE
        spreadsheet_credentials = json.loads(self.env.GOOGLE_SHEET_CREDENTIALS)

        credentials = service_account.Credentials.from_service_account_info(spreadsheet_credentials, scopes=SCOPES)
        try:
            service = build('sheets', 'v4', credentials=credentials)

            # Call the Sheets API
            sheet = service.spreadsheets()
            result = sheet.values().get(spreadsheetId=spreadsheet_id,
                                        range=spreadsheet_range).execute()
            values = result.get('values', [])

            if not values:
                logger.info('No data found in spreadsheet')
                return []

            return values
        except HttpError as err:
            logger.exception(f"Google sheets error: %s", err)
            raise
