from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.assistant.models import AssistantBot, AssistantNote, Chat, ChatMessage
from apps.common.admin import ModelAdmin, ReadOnlyHiddenModelAdmin, TabularInline


@admin.register(Chat)
class ChatAdmin(ModelAdmin[Chat]):
    class ChatMessageInline(TabularInline[ChatMessage]):
        model = ChatMessage
        verbose_name = _("Chat Messages")
        verbose_name_plural = _("Chat Messages")

    inlines = (ChatMessageInline,)


@admin.register(ChatMessage)
class ChatMessageAdmin(ReadOnlyHiddenModelAdmin[ChatMessage]):
    pass


@admin.register(AssistantNote)
class AssistantNoteAdmin(ModelAdmin[AssistantNote]):
    pass


@admin.register(AssistantBot)
class AssistantBotAdmin(ModelAdmin[AssistantBot]):
    pass
