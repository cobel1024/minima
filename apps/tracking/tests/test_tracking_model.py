import pytest
from django.conf import settings
from mimesis import Generic
from pytest_mock.plugin import MockerFixture

from apps.account.models import User
from apps.tracking.models import HotEvent


@pytest.mark.django_db
def test_tracking(mimesis: Generic, mocker: MockerFixture):
    initial_count = HotEvent.objects.count()

    user, _ = User.objects.get_or_create(email=mimesis.person.email(), defaults={"name": mimesis.person.full_name()})

    name = user.name
    user.name = f"{mimesis.person.full_name()} {mimesis.random.randint(0, 100)}"
    user.save()

    user.name = name
    user.save()

    sync_result = HotEvent.sync()
    assert sync_result["synced_count"] > 0

    user_events = HotEvent.objects.filter(pgh_obj_id=user.id).count()
    assert user_events > 0

    mocker.patch.object(settings, "HOT_EVENTS_RETENTION_DAYS", 0)

    cleanup_result = HotEvent.cleanup()

    final_count = HotEvent.objects.count()
    assert final_count == 0
    assert cleanup_result["deleted_count"] == initial_count + sync_result["synced_count"]
