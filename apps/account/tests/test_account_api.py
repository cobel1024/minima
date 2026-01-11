import base64
import json
from datetime import timedelta

import pyotp
import pytest
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.test.client import Client
from django.utils import timezone
from mimesis import ImageFile
from mimesis.providers.generic import Generic

from apps.account.models import TempPassword, User
from apps.common.error import ErrorCode
from apps.common.models import tuid


@pytest.mark.e2e
@pytest.mark.django_db
def test_account_flow(client: Client, token_spy: list[str], mimesis: Generic):
    # join policies
    res = client.get("/api/v1/operation/policyversion/join")
    assert res.status_code == 200, "join policies"
    policy_agreements = [str(policy["effectiveVersion"]["id"]) for policy in res.json()]

    person = mimesis.person

    new_user = {
        "name": person.name(),
        "email": f"{tuid(12)}.{person.email()}",
        "password": person.password(),
        "callbackUrl": mimesis.internet.url(),
        "agreements": policy_agreements,
    }

    # join
    res = client.post("/api/v1/account/join", data=json.dumps(new_user), content_type="application/json")
    assert res.status_code == 200, "join"

    # requestactivation
    res = client.post(
        "/api/v1/account/requestactivation",
        data=json.dumps({"email": new_user["email"], "callbackUrl": new_user["callbackUrl"]}),
        content_type="application/json",
    )
    assert res.status_code == 200, "requestactivation"

    # activate
    res = client.post(
        "/api/v1/account/activate", data=json.dumps({"token": token_spy.pop()}), content_type="application/json"
    )
    assert res.status_code == 200, "activate"

    # requestpasswordchange
    res = client.post(
        "/api/v1/account/requestpasswordchange",
        data=json.dumps({"email": new_user["email"], "callbackUrl": new_user["callbackUrl"]}),
        content_type="application/json",
    )
    assert res.status_code == 200, "requestpasswordchange"

    # applypasswordchange
    new_user["password"] = person.password()
    res = client.post(
        "/api/v1/account/applypasswordchange",
        data=json.dumps({"token": token_spy.pop(), "password": new_user["password"]}),
        content_type="application/json",
    )
    assert res.status_code == 200, "applypasswordchange"

    # login
    res = client.post(
        "/api/v1/account/login",
        data=json.dumps({"email": new_user["email"], "password": new_user["password"]}),
        content_type="application/json",
    )
    assert res.status_code == 200, "login"

    # get_me
    res = client.get("/api/v1/account/me")
    assert res.status_code == 200, "get_me"

    # update_me
    res = client.post("/api/v1/account/me", data=json.dumps({"name": person.name()}), content_type="application/json")
    assert res.status_code == 200, "update_me"

    # update_avatar
    image = ContentFile(mimesis.binaryfile.image(file_type=ImageFile.PNG), "avatar.png")
    res = client.post("/api/v1/account/me/avatar", data={"avatarFile": image}, format="multipart")
    assert res.status_code == 200, "update_avatar"

    # requestemailchange
    new_user["email"] = f"{tuid(8)}.{person.email()}"
    res = client.post(
        "/api/v1/account/requestemailchange",
        data=json.dumps({
            "newEmail": new_user["email"],
            "password": new_user["password"],
            "callbackUrl": new_user["callbackUrl"],
        }),
        content_type="application/json",
    )
    assert res.status_code == 200, "requestemailchange"

    # applyemailchange
    token = token_spy.pop()
    res = client.post(
        "/api/v1/account/applyemailchange", data=json.dumps({"token": token}), content_type="application/json"
    )
    assert res.status_code == 200, "applyemailchange"

    # login with new email
    res = client.post(
        "/api/v1/account/login",
        data=json.dumps({"email": new_user["email"], "password": new_user["password"]}),
        content_type="application/json",
    )
    assert res.status_code == 200, "login with new email"
    login_user = res.json()

    # reaction
    res = client.post(
        "/api/v1/account/reaction",
        data=json.dumps({"targetId": login_user["id"], "appLabel": "account", "model": "user", "kind": "bookmark"}),
        content_type="application/json",
    )
    assert res.status_code == 200, "save reaction"

    # reaction
    res = client.get("/api/v1/account/reaction")
    bookmarked_item = res.json()["items"][:1][0]
    assert bookmarked_item["kind"] == "bookmark" and bookmarked_item["targetId"] == login_user["id"], "get reactions"

    # setup otp
    res = client.post("/api/v1/account/otp/setup")
    assert res.status_code == 200, "setup otp"

    # complete otp setup
    secret_key = res.json()["secretKey"]
    secret_bytes = bytes.fromhex(secret_key)
    secret_base32 = base64.b32encode(secret_bytes).decode()
    code = pyotp.totp.TOTP(secret_base32).now()
    res = client.post(
        "/api/v1/account/otp/setup/complete",
        data=json.dumps({"code": code, "fingerprint": "browser-fingerprint" * 2}),
        content_type="application/json",
    )
    assert res.status_code == 200, "complete otp setup"

    # reset otp
    res = client.post("/api/v1/account/otp/reset")
    assert res.status_code == 200, "reset otp"

    # logout
    res = client.post("/api/v1/account/logout")
    assert res.status_code == 200, "logout"

    # admin create user
    admin_create_user = User.objects.create(
        email=f"{tuid(12)}.{person.email()}",
        name=person.name(),
        password="",  # empty password
        is_active=True,
    )

    # temporary password
    admin_set_password = person.password()
    TempPassword.objects.create(
        password=make_password(admin_set_password),
        user_id=admin_create_user.id,
        expires=timezone.now() + timedelta(hours=1),
    )

    # login with temporary password
    res = client.post(
        "/api/v1/account/login",
        data=json.dumps({"email": admin_create_user.email, "password": admin_set_password}),
        content_type="application/json",
    )
    assert res.status_code == 400, "login with temporary password"
    assert res.json()["detail"] == ErrorCode.PASSWORD_CHANGE_REQUIRED
