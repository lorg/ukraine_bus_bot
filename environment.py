import os


class Environment:
    """"A holder for environment variables, for loading only on requests, to make the code more easily testable"""

    def __init__(self):
        # pylint: disable=C0103
        self.ENV_NAME = os.environ.get('ENV_NAME')

        self.TEXTS_TABLE = os.environ.get('TEXTS_TABLE', "texts_table_test")
        self.BLASTS_TABLE = os.environ.get('BLASTS_TABLE', "blasts_table_test")
        self.BLAST_PHONES_TABLE = os.environ.get('BLAST_PHONES_TABLE', 'blast_phones_table_test')

        self.SOURCE_NUMBER = os.environ.get('SOURCE_NUMBER', '').strip()
        self.TEST_NUMBERS = os.environ.get('TEST_NUMBERS', '').strip()
        self.SMS_SOURCE_NUMBERS = os.environ.get(
            'SMS_SOURCE_NUMBERS', '').strip()

        self.WEBHOOK_TOKEN = os.environ.get('WEBHOOK_TOKEN', '').strip()
        # self.ROOKOUT_TOKEN = os.environ.get('ROOKOUT_TOKEN', '').strip()
        # self.RUN_ROOKOUT = int(os.environ.get('RUN_ROOKOUT', '0').strip())
        self.TIMEOUT_STEP_FUNC_ARN = os.environ.get(
            'TIMEOUT_STEP_FUNC_ARN', '').strip()

        self.TWILIO_ACCOUNT_SID = os.environ.get(
            'TWILIO_ACCOUNT_SID', '').strip()
        self.TWILIO_AUTH_TOKEN = os.environ.get(
            'TWILIO_AUTH_TOKEN', '').strip()
        # self.ADMIN_NUMBERS = [num for num in os.environ.get(
        #     'ADMIN_NUMBERS', '').split(',') if num]
        # self.TESTING_NUMBERS = [num for num in os.environ.get(
        #     'TESTING_NUMBERS', '').split(',') if num]

        self.WASSENGER_API_KEY = os.environ.get('WASSENGER_API_KEY', '')
        self.SOURCE_DEVICE = os.environ.get('SOURCE_DEVICE', '')
        self.ADMIN_MESSAGES_SOURCE_DEVICE = os.environ.get(
            'ADMIN_MESSAGES_SOURCE_DEVICE', '')

        self.GOOGLE_SHEETS_LOG_URL = os.environ.get('GOOGLE_SHEETS_LOG_URL', '')

        # self.SENTRY_DSN = os.environ.get('SENTRY_DSN', '').strip()

        # self.APIGATEWAY_URL = os.environ.get('APIGATEWAY_URL', '').strip()
