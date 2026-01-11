import json
from typing import cast

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test.client import Client
from mimesis.providers.generic import Generic

from apps.content.api.schema import WatchInSchema, WatchOutSchema
from apps.content.models import Media
from apps.content.tests.factories import MediaFactory
from apps.learning.tests.factories import EnrollmentFactory
from conftest import AdminUser

UNWATCH = "0"
WATCH = "1"


@pytest.mark.e2e
@pytest.mark.django_db
def test_media_flow(client: Client, admin_user: AdminUser, mimesis: Generic):
    admin_user.login()

    media = cast(Media, MediaFactory())
    EnrollmentFactory(
        content_type=ContentType.objects.get_for_model(media), content_id=media.id, active=True, user_id=admin_user.id
    )
    media_id = media.id

    # get media
    res = client.get(f"/api/v1/content/media/{media_id}")
    assert res.status_code == 200, f"get media {media_id}"

    media = res.json()

    # get subtitles
    res = client.get(f"/api/v1/content/media/{media_id}/subtitle")
    assert res.status_code == 200, f"get subtitles {media_id}"

    # first watch
    first_watch = WatchOutSchema.model_validate({"last_position": 0, "watch_bits": "0" * int(media["durationSeconds"])})
    res = client.post(
        f"/api/v1/content/media/{media_id}/watch",
        data=json.dumps(first_watch.model_dump()),
        content_type="application/json",
    )
    assert res.status_code == 200, f"first watch {media_id}"

    # get watch
    res = client.get(f"/api/v1/content/media/{media_id}/watch")
    assert res.status_code == 200, f"get watch {media_id}"

    watch = WatchInSchema.model_validate(res.json())
    assert len(watch.watch_bits) == media["durationSeconds"], "watch bits length"

    # update watch
    watch.watch_bits = watch.watch_bits.replace(UNWATCH, WATCH, 1)
    updated_watch_len = watch.watch_bits.count(WATCH)

    new_watch = WatchOutSchema.model_validate(watch.model_dump())
    res = client.post(
        f"/api/v1/content/media/{media_id}/watch",
        data=json.dumps(new_watch.model_dump()),
        content_type="application/json",
    )
    assert res.status_code == 200, f"update watch {media_id}"

    res = client.get(f"/api/v1/content/media/{media_id}/watch")
    updateed_watch_len_from_server = WatchInSchema.model_validate(res.json()).watch_bits.count(WATCH)
    assert updated_watch_len == updateed_watch_len_from_server, "update watch bits length"

    # create or update note
    note = mimesis.text.text()
    res = client.post(f"/api/v1/content/media/{media_id}/note", data={"note": note}, format="multipart")
    assert res.status_code == 200, f"create or update note {media_id}"

    # delete watch
    res = client.delete(f"/api/v1/content/media/{media_id}/watch")
    assert res.status_code == 200, f"delete watch {media_id}"
