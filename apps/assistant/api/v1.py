import asyncio
import json
from typing import Annotated

from django.conf import settings
from django.http import StreamingHttpResponse
from django.http.response import Http404
from django.utils import timezone
from ninja.files import UploadedFile
from ninja.pagination import paginate
from ninja.params import Form, functions
from ninja.router import Router

from apps.assistant.api.schema import (
    AssistantNoteSaveSchema,
    ChatListSchema,
    ChatMessageCreateSchema,
    ChatMessageSchema,
    ChatMessageUpdateSchema,
    ChatSchema,
)
from apps.assistant.models import AssistantNote, Chat, ChatMessage
from apps.common.util import HttpRequest, Pagination

router = Router(by_alias=True)


@router.post("/note")
async def save_assistant_note(request: HttpRequest, data: AssistantNoteSaveSchema):
    await AssistantNote.objects.aupdate_or_create(user_id=request.auth, defaults={"note": data.note})


@router.post(
    "/chat/message",
    openapi_extra={
        "responses": {
            200: {
                "description": "Server-Sent Events stream (OpenAPI 3.2 itemSchema)",
                "content": {"text/event-stream": {}},
            }
        }
    },
)
async def create_chat_message(
    request: HttpRequest,
    data: Form[ChatMessageCreateSchema],
    files: Annotated[
        list[UploadedFile], functions.File(None, description=f"Max size: {settings.ATTACHMENT_MAX_SIZE_MB}MB")
    ],
):
    if files:
        ChatMessage.validate_files(files)

    # create message
    message = await ChatMessage.create(user_id=request.auth, **data.model_dump(exclude_unset=True), files=files)

    async def stream_generator():
        try:
            # new chat
            if not data.chat_id:
                chat_data = ChatSchema.from_orm(message.chat).model_dump_json(by_alias=True)
                yield f"event: chat\ndata: {chat_data}\n\n".encode("utf-8")

            # message
            message_data = ChatMessageSchema.from_orm(message).model_dump_json(by_alias=True)
            yield f"event: message\ndata: {message_data}\n\n".encode("utf-8")

            # stream
            try:
                raise ValueError("Unknown agent or agent key error")

                plugin = message.chat.bot.get_plugin()
                async for chunk in plugin.execute_stream(message=message, user_id=request.auth):
                    message.response += chunk
                    chunk_data = json.dumps({"response": chunk}, ensure_ascii=False)
                    yield f"event: chunk\ndata: {chunk_data}\n\n".encode("utf-8")
            except ValueError:
                # unknown agent or agent key error
                # echo test
                chunk_size = 10
                for i in range(0, len(message.message), chunk_size):
                    await asyncio.sleep(0.5)
                    chunk = message.message[i : i + chunk_size]
                    message.response += chunk
                    chunk_data = json.dumps({"response": chunk}, ensure_ascii=False)
                    yield f"event: chunk\ndata: {chunk_data}\n\n".encode("utf-8")

            # final
            now = timezone.now()
            message.completed = now

            final_data = json.dumps({"completed": now.isoformat()}, ensure_ascii=False)
            yield f"event: done\ndata: {final_data}\n\n".encode("utf-8")

        finally:
            await message.asave()

    return StreamingHttpResponse(stream_generator(), content_type="text/event-stream")


@router.post("/chat/message/{id}")
async def update_chat_message(request: HttpRequest, id: int, data: ChatMessageUpdateSchema):
    count = await ChatMessage.objects.filter(id=id, chat__user_id=request.auth).aupdate(**data.dict(exclude_unset=True))
    if not count:
        raise Http404


@router.get("/chat", response=ChatListSchema)
async def get_chats(request: HttpRequest):
    return await Chat.user_chats(request.auth)


@router.delete("/chat/{id}")
async def delete_chat(request: HttpRequest, id: int):
    count, _ = await Chat.objects.filter(user_id=request.auth, id=id).adelete()
    if not count:
        raise Http404


@router.get("/chat/{id}/message", response=list[ChatMessageSchema])
@paginate(Pagination)
async def get_chat_messages(request: HttpRequest, id: int):
    return (
        ChatMessage.objects
        .prefetch_related("attachments")
        .filter(chat_id=id, chat__user_id=request.auth)
        .order_by("-id")
    )
