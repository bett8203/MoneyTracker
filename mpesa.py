import os
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# =========================================================
# M-PESA SETTINGS
# =========================================================

CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
SHORTCODE = os.getenv("MPESA_SHORTCODE")
PASSKEY = os.getenv("MPESA_PASSKEY")
CALLBACK_URL = os.getenv("MPESA_CALLBACK_URL")

ENVIRONMENT = os.getenv(
    "MPESA_ENVIRONMENT",
    "sandbox"
).lower()


# =========================================================
# BASE URL
# =========================================================

if ENVIRONMENT == "production":

    BASE_URL = "https://api.safaricom.co.ke"

else:

    BASE_URL = "https://sandbox.safaricom.co.ke"


# =========================================================
# VALIDATE SETTINGS
# =========================================================

def validate_settings():

    missing = []

    if not CONSUMER_KEY:
        missing.append("MPESA_CONSUMER_KEY")

    if not CONSUMER_SECRET:
        missing.append("MPESA_CONSUMER_SECRET")

    if not SHORTCODE:
        missing.append("MPESA_SHORTCODE")

    if not PASSKEY:
        missing.append("MPESA_PASSKEY")

    if not CALLBACK_URL:
        missing.append("MPESA_CALLBACK_URL")

    if missing:

        raise Exception(
            "Missing M-Pesa settings: "
            + ", ".join(missing)
        )


# =========================================================
# FORMAT PHONE NUMBER
# =========================================================

def format_phone_number(phone_number):

    phone_number = str(phone_number).strip()

    # 0712345678 -> 254712345678
    if phone_number.startswith("07"):

        phone_number = (
            "254" + phone_number[1:]
        )

    # 0112345678 -> 254112345678
    elif phone_number.startswith("01"):

        phone_number = (
            "254" + phone_number[1:]
        )

    # +254712345678 -> 254712345678
    elif phone_number.startswith("+254"):

        phone_number = phone_number[1:]

    # Already 254...
    elif phone_number.startswith("254"):

        pass

    else:

        raise ValueError(
            "Invalid Kenyan M-Pesa phone number."
        )

    if not phone_number.isdigit():

        raise ValueError(
            "Phone number must contain numbers only."
        )

    if len(phone_number) != 12:

        raise ValueError(
            "Phone number must contain 12 digits."
        )

    if not phone_number.startswith("254"):

        raise ValueError(
            "Invalid Kenyan phone number."
        )

    return phone_number


# =========================================================
# GET ACCESS TOKEN
# =========================================================

def get_access_token():

    validate_settings()

    credentials = (
        f"{CONSUMER_KEY}:{CONSUMER_SECRET}"
    )

    encoded_credentials = base64.b64encode(
        credentials.encode("utf-8")
    ).decode("utf-8")

    headers = {
        "Authorization":
            f"Basic {encoded_credentials}"
    }

    url = (
        f"{BASE_URL}/oauth/v1/generate"
        "?grant_type=client_credentials"
    )

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    print("M-PESA TOKEN STATUS:")
    print(response.status_code)

    if response.status_code != 200:

        print(
            "M-PESA TOKEN RESPONSE:"
        )

        print(response.text)

        raise Exception(
            "Unable to obtain M-Pesa access token."
        )

    data = response.json()

    access_token = data.get(
        "access_token"
    )

    if not access_token:

        raise Exception(
            "Access token was not returned."
        )

    return access_token


# =========================================================
# STK PUSH
# =========================================================

def stk_push(
    phone_number,
    amount,
    account_reference="MoneyTracker LTD",
    transaction_description="MoneyTracker LTD Deposit"
):

    # -----------------------------------------------------
    # VALIDATE AMOUNT
    # -----------------------------------------------------

    try:

        amount = float(amount)

    except (TypeError, ValueError):

        raise ValueError(
            "Invalid M-Pesa amount."
        )

    if amount <= 0:

        raise ValueError(
            "Amount must be greater than zero."
        )

    # M-Pesa STK amount should be an integer
    amount = int(round(amount))

    if amount < 1:

        raise ValueError(
            "M-Pesa amount must be at least 1."
        )

    # -----------------------------------------------------
    # FORMAT PHONE
    # -----------------------------------------------------

    phone_number = format_phone_number(
        phone_number
    )

    # -----------------------------------------------------
    # GET TOKEN
    # -----------------------------------------------------

    token = get_access_token()

    # -----------------------------------------------------
    # TIMESTAMP
    # -----------------------------------------------------

    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )

    # -----------------------------------------------------
    # PASSWORD
    # -----------------------------------------------------

    password_string = (
        SHORTCODE
        + PASSKEY
        + timestamp
    )

    password = base64.b64encode(
        password_string.encode("utf-8")
    ).decode("utf-8")

    # -----------------------------------------------------
    # HEADERS
    # -----------------------------------------------------

    headers = {

        "Authorization":
            f"Bearer {token}",

        "Content-Type":
            "application/json"

    }

    # -----------------------------------------------------
    # STK PAYLOAD
    # -----------------------------------------------------

    payload = {

        "BusinessShortCode":
            SHORTCODE,

        "Password":
            password,

        "Timestamp":
            timestamp,

        "TransactionType":
            "CustomerPayBillOnline",

        "Amount":
            amount,

        "PartyA":
            phone_number,

        "PartyB":
            SHORTCODE,

        "PhoneNumber":
            phone_number,

        "CallBackURL":
            CALLBACK_URL,

        "AccountReference":
            account_reference,

        "TransactionDesc":
            transaction_description

    }

    # -----------------------------------------------------
    # PRINT DEBUG INFORMATION
    # -----------------------------------------------------

    print()
    print("==============================")
    print("M-PESA STK PUSH")
    print("==============================")

    print(
        "Phone:",
        phone_number
    )

    print(
        "Amount:",
        amount
    )

    print(
        "Account Reference:",
        account_reference
    )

    print(
        "Callback URL:",
        CALLBACK_URL
    )

    # -----------------------------------------------------
    # SEND REQUEST
    # -----------------------------------------------------

    url = (
        f"{BASE_URL}"
        "/mpesa/stkpush/v1/processrequest"
    )

    try:

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

    except requests.RequestException as error:

        print(
            "M-Pesa connection error:"
        )

        print(error)

        raise Exception(
            "Could not connect to M-Pesa."
        )

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    print(
        "STATUS CODE:",
        response.status_code
    )

    print(
        "RESPONSE:"
    )

    print(
        response.text
    )

    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    if response.status_code == 200:

        try:

            data = response.json()

        except ValueError:

            raise Exception(
                "M-Pesa returned an invalid response."
            )

        return data

    # -----------------------------------------------------
    # ERROR
    # -----------------------------------------------------

    try:

        error_data = response.json()

        error_message = (
            error_data.get(
                "errorMessage"
            )
            or error_data.get(
                "errorCode"
            )
            or response.text
        )

    except ValueError:

        error_message = response.text

    raise Exception(
        f"M-Pesa STK Push failed. "
        f"Status: {response.status_code}. "
        f"Response: {error_message}"
    )