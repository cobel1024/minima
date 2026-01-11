import base64
import json
import os

import pyotp
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test.client import Client
from django.utils import timezone
from mimesis import Generic, random
from pytest_django import DjangoDbBlocker
from pytest_mock import MockerFixture

from apps.common.error import ErrorCode
from apps.common.util import TokenDict, encode_token

random.global_seed = 0xFF


User = get_user_model()


@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture
def db_no_rollback(django_db_setup: None, django_db_blocker: DjangoDbBlocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


@pytest.fixture
def mimesis():
    return Generic(locale=settings.DEFAULT_LANGUAGE)


test_user_email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
test_user_password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "1111")


class AdminUser:
    def __init__(self, client: Client):
        self.client = client
        self.email = test_user_email
        self.password = test_user_password
        self.name = "Test Admin"
        self.logged_in = False
        self.id = None
        self.otp_secret_key = None

    def login(self):
        data = {"email": self.email, "password": self.password}
        res = self.client.post("/api/v1/account/login", data=json.dumps(data), content_type="application/json")
        assert res.status_code == 200, "test admin login"
        user_dict = res.json()
        self.id = user_dict["id"]
        self.logged_in = True
        return user_dict

    def logout(self):
        res = self.client.post("/api/v1/account/logout")
        assert res.status_code == 200, "test admin logout"
        self.id = None
        self.logged_in = False

    def get_user(self):
        return User.objects.get(email=self.email)

    def setup_otp(self):
        self.client.post("/api/v1/account/otp/reset")
        res = self.client.post("/api/v1/account/otp/setup")
        self.otp_secret_key = res.json()["secretKey"]
        secret_base32 = base64.b32encode(bytes.fromhex(self.otp_secret_key)).decode().rstrip("=")
        code = pyotp.TOTP(secret_base32).now()
        res = self.client.post(
            "/api/v1/account/otp/setup/complete",
            data=json.dumps({"code": code, "fingerprint": "a" * 32}),
            content_type="application/json",
        )
        assert res.status_code == 200, "complete otp setup"

    def verify_otp(self, token: str):
        if not self.otp_secret_key:
            raise ValueError(ErrorCode.OTP_NOT_SETUP)

        secret_base32 = base64.b32encode(bytes.fromhex(self.otp_secret_key)).decode().rstrip("=")
        totp = pyotp.TOTP(secret_base32)
        code = totp.at(int(timezone.now().timestamp() + 31))
        res = self.client.post(
            "/api/v1/account/otp/verify",
            data=json.dumps({"token": token, "code": code, "fingerprint": "a" * 32}),
            content_type="application/json",
        )
        assert res.status_code == 200, "otp verify"


@pytest.fixture
def admin_user(client: Client):
    return AdminUser(client)


@pytest.fixture
def token_spy(mocker: MockerFixture):
    original_encode = encode_token
    captured_tokens: list[str] = []

    def spy_encode_token(payload: TokenDict):
        token = original_encode(payload)
        captured_tokens.append(token)
        return token

    mocker.patch("apps.common.util.encode_token", side_effect=spy_encode_token)
    mocker.patch("apps.account.models.encode_token", side_effect=spy_encode_token)
    return captured_tokens


def parse_sse(chunks):
    buffer = b"".join(chunks).decode("utf-8")
    events = []

    for block in buffer.strip().split("\n\n"):
        event = None
        data = None

        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()

            elif line.startswith("data:"):
                payload = line[5:].strip()
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    data = payload

        if event is not None:
            events.append({"event": event, "data": data})

    return events
