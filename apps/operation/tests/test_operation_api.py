import json

import pytest
from django.core.files.base import ContentFile
from django.test.client import Client
from mimesis.enums import ImageFile
from mimesis.providers.generic import Generic

from apps.operation.tests.factories import MessageFactory
from conftest import AdminUser


@pytest.mark.e2e
@pytest.mark.django_db
def test_inquiry_flow(client: Client, admin_user: AdminUser, mimesis: Generic):
    admin_user.login()

    # get inquiries
    res = client.get("/api/v1/operation/inquiry")
    assert res.status_code == 200, "get inquiries"

    # create inquiry
    files = [ContentFile(mimesis.binaryfile.image(file_type=ImageFile.PNG), "avatar.png") for _ in range(2)]
    res = client.post(
        "/api/v1/operation/inquiry",
        data={
            "title": mimesis.text.title(),
            "question": mimesis.text.text(),
            "appLabel": "account",
            "model": "user",
            "contentId": admin_user.id,
            "files": files,
        },
        format="multipart",
    )
    assert res.status_code == 200, "create inquiry"


@pytest.mark.e2e
@pytest.mark.django_db
def test_message_flow(client: Client, admin_user: AdminUser, mimesis: Generic):
    admin_user.login()

    MessageFactory.create(user=admin_user.get_user())

    # get messages
    res = client.get("/api/v1/operation/message")
    assert res.status_code == 200, "get messages"

    # get message
    items = res.json()["items"]
    message_id = items[-1]["id"]
    res = client.get(f"/api/v1/operation/message/{message_id}")
    assert res.status_code == 200, "get message"


@pytest.mark.e2e
@pytest.mark.django_db
def test_policy_flow(client: Client, admin_user: AdminUser):
    # get join policies
    res = client.get("/api/v1/operation/policyversion/join")
    assert res.status_code == 200, "get join policies"

    join_policies: dict[str, bool] = {}
    for policy in res.json():
        join_policies[str(policy["effectiveVersion"]["id"])] = True

    # login
    admin_user.login()

    # agree join policies
    res = client.post(
        "/api/v1/operation/policyversion/agree", data=json.dumps(join_policies), content_type="application/json"
    )
    assert res.status_code == 200, "agree join policies"


@pytest.mark.e2e
@pytest.mark.django_db
def test_thread_flow(client: Client, admin_user: AdminUser, mimesis: Generic):
    admin_user.login()

    text = mimesis.text

    # create thread
    thread_data = {
        "title": text.sentence(),
        "appLabel": "account",
        "model": "user",
        "subjectId": admin_user.id,
        "description": text.text(),
        "deadline": None,
    }
    res = client.post("/api/v1/operation/thread", data=json.dumps(thread_data), content_type="application/json")
    assert res.status_code == 200, "create thread"

    # get thread
    res = client.get(f"/api/v1/operation/thread/account/user/subject/{admin_user.id}")
    assert res.status_code == 200, "get thread"
    thread_id = res.json()["id"]

    # get comments
    res = client.get(f"/api/v1/operation/thread/{thread_id}/comment")
    assert res.status_code == 200, "get comments"
    comment_count = res.json()["count"]

    # create comment
    created_comment_id = None
    for _ in range(3):
        comment_data = {"comment": text.text(), "threadId": thread_id}
        res = client.post(f"/api/v1/operation/thread/{thread_id}/comment", data=comment_data, format="multipart")
        assert res.status_code == 200, "create comment"
        if created_comment_id is None:
            created_comment_id = res.json()["id"]

        # create child comment
        for _ in range(3):
            child_comment_data = {"comment": text.text(), "threadId": thread_id, "parentId": res.json()["id"]}
            res = client.post(
                f"/api/v1/operation/thread/{thread_id}/comment", data=child_comment_data, format="multipart"
            )
            assert res.status_code == 200, "create child comment"

    # get comments
    res = client.get(f"/api/v1/operation/thread/{thread_id}/comment")
    assert res.status_code == 200, "get comments again"
    assert res.json()["count"] == 3 + comment_count, "comments count after create"

    # delete comment
    res = client.delete(f"/api/v1/operation/thread/{thread_id}/comment/{created_comment_id}")
    assert res.status_code == 200, "delete comment"

    # get comments
    res = client.get(f"/api/v1/operation/thread/{thread_id}/comment")
    assert res.status_code == 200, "get comments"
    assert res.json()["count"] == 3 + comment_count, "comments count after soft delete"
    assert res.json()["items"][-1]["deleted"] is True, "comment deleted"
