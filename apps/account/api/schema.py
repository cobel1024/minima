from datetime import date, datetime
from typing import Annotated, Literal

from django.conf import settings
from django.core.exceptions import ValidationError
from phonenumber_field.validators import validate_international_phonenumber
from pydantic.fields import Field
from pydantic.functional_validators import field_validator
from pydantic.networks import EmailStr, HttpUrl
from pydantic_core._pydantic_core import PydanticCustomError

from apps.common.schema import ContentTypeSchema, Schema, TimeStampedMixinSchema

Language = Literal["en", "ko", ""]


class LoginSchema(Schema):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=50)]


class UserSchema(TimeStampedMixinSchema):
    id: str
    email: str
    name: str
    avatar: str | None
    birth_date: date | None
    nickname: str
    language: Language
    phone: str
    preferences: Annotated[dict[str, bool | str | int], Field(None)]
    is_active: bool
    otp_enabled: datetime | None
    token_expires: datetime | None

    @staticmethod
    def resolve_phone(obj):
        if not obj.phone:
            return ""
        return str(obj.phone)


class JoinSchema(Schema):
    name: Annotated[str, Field(min_length=2, max_length=50)]
    email: EmailStr
    password: Annotated[str, Field(min_length=settings.PASSWORD_MIN_LENGTH, max_length=50)]
    agreements: list[str]
    callback_url: HttpUrl


class RequestactivationSchema(Schema):
    email: EmailStr
    callback_url: HttpUrl


class AccountActivateSchema(Schema):
    token: Annotated[str, Field(min_length=32)]


class UserUpdateSchema(Schema):
    name: Annotated[str, Field(None, min_length=2, max_length=50)]
    nickname: Annotated[str, Field(None)]
    phone: Annotated[str, Field(None)]
    birth_date: Annotated[date | None, Field(None)]
    language: Annotated[Language, Field(None)]
    preferences: Annotated[dict[str, bool | str | int], Field(None)]

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v):
        try:
            validate_international_phonenumber(v)
        except ValidationError:
            raise PydanticCustomError("invalid_phone", "INVALID_PHONE")
        return v


class RequestEmailChangeSchema(Schema):
    new_email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=50)]
    callback_url: HttpUrl


class ApplyEmailChangeSchema(Schema):
    token: Annotated[str, Field(min_length=32)]


class RequestPasswordChangeSchema(Schema):
    email: EmailStr
    callback_url: HttpUrl


class ApplyPasswordChangeSchema(Schema):
    password: Annotated[str, Field(min_length=settings.PASSWORD_MIN_LENGTH, max_length=50)]
    token: Annotated[str, Field(min_length=32)]


ReactionKind = Literal["like", "flag", "bookmark"]


class ReactionSchema(TimeStampedMixinSchema):
    id: int
    kind: ReactionKind
    target_type: ContentTypeSchema
    target_id: str


class ReactionSaveSchema(Schema):
    kind: ReactionKind | None  # None means delete
    target_id: str
    app_label: str
    model: str


class TOTPDeviceSchema(Schema):
    id: int
    name: str
    created_at: datetime
    confirmed: bool


class OtpSetupSchema(Schema):
    qr_code: str
    backup_codes: list[str]
    secret_key: str


class OtpSetupCompleteSchema(Schema):
    code: Annotated[str, Field(min_length=6, max_length=6)]
    fingerprint: Annotated[str, Field(min_length=32)]


class OtpVerifySchema(Schema):
    token: Annotated[str, Field(min_length=32)]
    code: Annotated[str, Field(min_length=6, max_length=6)]
    fingerprint: str


class OwnerSchema(Schema):
    id: str
    name: str
    email: str
    avatar: str | None
    nickname: str
