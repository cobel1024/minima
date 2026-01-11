from datetime import datetime
from typing import Annotated

from pydantic.fields import Field

from apps.assistant.models import ChatMessage
from apps.common.schema import Schema


class AssistantNoteSaveSchema(Schema):
    note: str


class AssistantBotSchema(Schema):
    name: str
    description: str
    avatar: str | None


class ChatSchema(Schema):
    id: int
    title: str
    active: bool
    message_count: int
    last_message: datetime | None
    bot: AssistantBotSchema


class ChatListSchema(Schema):
    chats: list[ChatSchema]
    assistant_note: str | None


class ChatMessageCreateSchema(Schema):
    message: str
    url: str
    chat_id: int | None = None
    bot_id: int | None = None


class ChatMessageSchema(Schema):
    id: int
    created: datetime
    modified: datetime
    message: str
    response: str
    url: str
    completed: datetime | None
    bookmarked: bool
    rating: int | None

    @staticmethod
    def resolve_message(obj: ChatMessage):
        return obj.cleaned_message

    @staticmethod
    def resolve_response(obj: ChatMessage):
        return obj.cleaned_response


class ChatMessageUpdateSchema(Schema):
    bookmarked: Annotated[bool, Field(None)]
    rating: Annotated[Annotated[int, Field(ge=1, le=5)] | None, Field(None)]
