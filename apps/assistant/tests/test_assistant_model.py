import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.assistant.tests.factories import AssistantBotFactory, AssistantNoteFactory, ChatFactory


@pytest.mark.order(-3)
@pytest.mark.django_db
def test_assistant():
    bot = AssistantBotFactory.create()
    ChatFactory.create(bot=bot)
    AssistantNoteFactory.create()


@pytest.mark.order(-3)
@pytest.mark.load_data
def test_load_assistant_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        bot = AssistantBotFactory.create()
        ChatFactory.create_batch(20, bot=bot)
        AssistantNoteFactory.create_batch(10)
