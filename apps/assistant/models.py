from typing import TYPE_CHECKING, Sequence

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.files.storage import storages
from django.db.models import (
    CASCADE,
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKey,
    ImageField,
    Model,
    OneToOneField,
    PositiveIntegerField,
    PositiveSmallIntegerField,
    Q,
    TextChoices,
    TextField,
)
from django.utils.translation import gettext_lazy as _

from apps.assistant.plugin.base import BasePlugin
from apps.assistant.plugin.registry import PluginRegistry
from apps.assistant.trigger import chat_ensure_single_active, chat_sync_message_count
from apps.common.error import ErrorCode
from apps.common.models import BooleanNowField, SoftDeleteMixin, TimeStampedMixin
from apps.operation.models import AttachmentMixin

User = get_user_model()


class AssistantBot(Model):
    class BotKind(TextChoices):
        ASSISTANT = "assistant", _("Assistant")
        CURATOR = "curator", _("Curator")

    name = CharField(_("Name"), max_length=50, unique=True)
    description = TextField(_("Description"), default="", blank=True)
    avatar = ImageField(_("Avatar"), null=True, blank=True, storage=storages["avatar"])
    kind = CharField(_("Plugin"), max_length=50, choices=BotKind.choices, default=BotKind.ASSISTANT)
    system_instruction = TextField(_("System Instruction"), default="", blank=True)

    class Meta:
        verbose_name = _("Assistant Bot")
        verbose_name_plural = _("Assistant Bots")

    def get_plugin(self) -> BasePlugin:
        plugin_class = PluginRegistry.get(self.kind)
        return plugin_class()


class AssistantNote(TimeStampedMixin):
    user = OneToOneField(User, CASCADE, verbose_name=_("User"))
    note = TextField(_("Note"), default="", blank=True)

    class Meta:
        verbose_name = _("Assistant Note")
        verbose_name_plural = _("Assistant Notes")


PUBLIC_HISTORY_COUNT = 10


class Chat(SoftDeleteMixin):
    title = CharField(_("Title"), max_length=255, default="", blank=True)
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    active = BooleanField(_("Active"), default=True)
    message_count = PositiveSmallIntegerField(_("Message Count"), default=0)
    last_message = DateTimeField(_("Last Message"), null=True, blank=True)
    bot = ForeignKey(AssistantBot, CASCADE, verbose_name=_("Bot"))

    class Meta:
        verbose_name = _("Chat")
        verbose_name_plural = _("Chats")

    if TYPE_CHECKING:
        user_id: str

    @classmethod
    async def user_chats(cls, user_id: str):
        note = await AssistantNote.objects.filter(user_id=user_id).afirst()
        chats = [
            c
            async for c in cls.objects
            .select_related("bot")
            .filter(user_id=user_id)
            .order_by("-id")[:PUBLIC_HISTORY_COUNT]
        ]
        return {"chats": chats, "assistant_note": note.note if note else None}


setattr(Chat._meta, "triggers", [chat_ensure_single_active(Chat._meta.db_table)])


class ChatMessage(SoftDeleteMixin, TimeStampedMixin, AttachmentMixin):
    chat = ForeignKey(Chat, CASCADE, verbose_name=_("Chat"))
    message = TextField(_("Message"), default="", blank=True)
    response = TextField(_("Response"), default="", blank=True)
    url = CharField(_("URL"), max_length=500, default="", blank=True)
    completed = BooleanNowField(_("Completed"), null=True, blank=True)
    bookmarked = BooleanField(_("Bookmarked"), default=False)
    rating = PositiveSmallIntegerField(_("Rating"), null=True, blank=True)
    input_tokens = PositiveIntegerField(_("Input Tokens"), null=True, blank=True)
    output_tokens = PositiveIntegerField(_("Output Tokens"), null=True, blank=True)

    class Meta:
        verbose_name = _("Chat Message")
        verbose_name_plural = _("Chat Messages")

    if TYPE_CHECKING:
        chat_id: int

    @property
    def cleaned_message(self):
        return self.update_attachment_urls(content=self.message)

    @property
    def cleaned_response(self):
        return self.update_attachment_urls(content=self.response)

    @classmethod
    async def create(
        cls,
        *,
        user_id: str,
        message: str,
        url: str,
        files: Sequence[File] | None,
        chat_id: int | None = None,
        bot_id: int | None = None,
    ):

        if chat_id:
            chat = await Chat.objects.select_related("bot").filter(user_id=user_id).aget(id=chat_id)
        else:
            q = Q(bot_id=bot_id) if bot_id else Q(kind=AssistantBot.BotKind.ASSISTANT)
            bot = await AssistantBot.objects.filter(q).afirst()
            if not bot:
                raise ValueError(ErrorCode.ASSISTANT_NOT_FOUND)
            title = BeautifulSoup(message, "html.parser").get_text(separator=" ", strip=True)[:50]
            chat = await Chat.objects.acreate(user_id=user_id, title=title or _("New Chat"), bot=bot)

        chat_message = await ChatMessage.objects.acreate(chat=chat, message=message, url=url)
        await chat_message.update_attachments(files=files, owner_id=user_id, content=chat_message.message)
        return chat_message


setattr(ChatMessage._meta, "triggers", chat_sync_message_count(Chat._meta.db_table, ChatMessage._meta.db_table))
