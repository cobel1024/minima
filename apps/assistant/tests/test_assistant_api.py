import json

import pytest
from django.test.client import Client
from django.utils import timezone
from mimesis.providers.generic import Generic

from apps.assistant.models import AssistantBot, ChatMessage
from conftest import AdminUser, parse_sse


@pytest.mark.e2e
@pytest.mark.django_db
def test_assistant_flow(client: Client, admin_user: AdminUser, mimesis: Generic, monkeypatch):
    admin_user.login()

    AssistantBot.objects.get_or_create(name="Assisttant")

    async def fake_execute_stream(self, message: ChatMessage, user_id: str):
        yield json.dumps({"id": message.pk, "message": message.message})
        yield json.dumps({"chunk": "fake"})
        yield json.dumps({"chunk": " ai response"})

        message.response = "fake ai response"
        message.completed = timezone.now()
        await message.asave()

        yield json.dumps({"done": True})

    monkeypatch.setattr("apps.assistant.plugin.assistant.AssistantPlugin.execute_stream", fake_execute_stream)

    res = client.post("/api/v1/assistant/note", data=json.dumps({"note": ""}), content_type="application/json")
    assert res.status_code == 200, "save note"

    res = client.get("/api/v1/assistant/chat")
    res.status_code == 200

    message_data = {"message": mimesis.text.sentence(), "url": f"/course/{mimesis.cryptographic.uuid()[:12]}"}
    res = client.post("/api/v1/assistant/chat/message", data=message_data, format="multipart")
    assert res.status_code == 200, "create message"

    data = parse_sse(list(res))

    chat_id = data[0]["data"]["id"]

    res = client.get(f"/api/v1/assistant/chat/{chat_id}/message")
    assert res.status_code == 200, "get chat messages"

    res = client.delete(f"/api/v1/assistant/chat/{chat_id}")
    assert res.status_code == 200, "delete chat"
