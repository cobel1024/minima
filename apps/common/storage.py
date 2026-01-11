import asyncio
import logging
import os
from typing import TYPE_CHECKING, TypedDict

from botocore.exceptions import ClientError
from django.contrib.staticfiles.storage import ManifestFilesMixin
from storages.backends.s3 import S3Storage

from apps.common.util import tuid

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from mypy_boto3_s3.service_resource import Bucket
    from mypy_boto3_s3.type_defs import ObjectIdentifierTypeDef


class PutUrlDict(TypedDict):
    key: str
    url: str
    mime_type: str


class ManifestStaticS3Storage(ManifestFilesMixin, S3Storage):
    # Non-hashed URL wibll be returned in debug mode.
    pass


UNIQUE_KEY_LENGTH = 6


class UniqueFilenameS3Storage(S3Storage):
    def generate_filename(self, filename):
        super().generate_filename(filename)
        name, ext = os.path.splitext(filename)
        return f"{name}.{tuid(UNIQUE_KEY_LENGTH)}{ext}"


class AvatarStorage(UniqueFilenameS3Storage):
    pass


class DefaultStorage(UniqueFilenameS3Storage):
    if TYPE_CHECKING:
        bucket: Bucket
        bucket_name: str
        location: str

    async def delete_objects(self, keys: set[str]):
        # Note: This method is used exceptionally.
        # File cleanup is automatically handled by django-cleanup in normal operations.

        if not keys:
            return

        def _delete_objects():
            try:
                delete_objects: list[ObjectIdentifierTypeDef] = [ObjectIdentifierTypeDef(Key=key) for key in keys]
                self.bucket.meta.client.delete_objects(Bucket=self.bucket_name, Delete={"Objects": delete_objects})
            except ClientError as e:
                log.error(e, exc_info=True)

        await asyncio.to_thread(_delete_objects)
