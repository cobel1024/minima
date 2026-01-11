import base64
import io
import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from time import time
from typing import TYPE_CHECKING, ClassVar, Literal, TypedDict

import pghistory
import qrcode
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.storage import storages
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, loads
from django.db.models import (
    CASCADE,
    BooleanField,
    CharField,
    DateField,
    DateTimeField,
    EmailField,
    F,
    ForeignKey,
    GenericIPAddressField,
    ImageField,
    Index,
    JSONField,
    Model,
    OneToOneField,
    TextChoices,
    TextField,
    UniqueConstraint,
)
from django.db.models.expressions import OuterRef, Subquery
from django.db.models.query import QuerySet
from django.db.utils import IntegrityError
from django.http.response import HttpResponse
from django.template.loader import get_template
from django.utils import timezone
from django.utils.translation import gettext as _
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from ipware.ip import get_client_ip
from jwt.exceptions import InvalidTokenError
from pghistory.models import PghEventModel
from phonenumber_field.modelfields import PhoneNumberField

from apps.common.error import ErrorCode
from apps.common.models import TimeStampedMixin, TuidMixin
from apps.common.util import HttpRequest, OtpTokenDict, TokenDict, decode_token, encode_token

log = logging.getLogger(__name__)


AuthTokenType = Literal["activation", "email_change", "password_change"]


class CookieDict(TypedDict):
    httponly: bool
    secure: bool
    samesite: Literal["Lax", "None", "Strict", False] | None
    path: str


def auth_cookie_options():
    return CookieDict(httponly=True, secure=not settings.DEBUG, samesite="Lax", path="/")


def load_template(template_path: str):
    return get_template(f"account/mail/{template_path}.html")


class PasswordChangeRequiredError(Exception):
    pass


class SetupOtpDict(TypedDict):
    qr_code: str
    backup_codes: list[str]
    secret_key: str


class UserManager(BaseUserManager["User"]):
    # We only use manager for operations that require queryset chaining.
    # However, create_superuser is already implemented in Django's manager pattern
    # and required by management commands, so we override it here reluctantly.

    def create_superuser(self, email: str, name: str, password: str, **extra_fields: object):
        user = self.model(email=email, name=name, is_superuser=True, is_active=True, is_staff=True, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


@pghistory.track(exclude=["password"])
class User(TuidMixin, TimeStampedMixin, AbstractBaseUser, PermissionsMixin):
    email = EmailField(_("Email"), unique=True)
    name = CharField(_("Name"), max_length=50)
    avatar = ImageField(_("Avatar"), null=True, blank=True, storage=storages["avatar"])
    nickname = CharField(_("Nickname"), max_length=50, blank=True, default="")
    phone = PhoneNumberField(_("Phone"), blank=True, default="")
    birth_date = DateField(_("Birth Date"), null=True, blank=True)
    language = CharField(_("Language"), max_length=10, blank=True, default="")
    preferences = JSONField(_("Preferences"), blank=True, default=dict)

    is_active = BooleanField(_("Active"), default=False)
    is_staff = BooleanField(_("Staff"), default=False)
    is_superuser = BooleanField(_("Superuser"), default=False)

    # Do not remove this. It will disable login state signal.
    last_login = None

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects: ClassVar[UserManager] = UserManager()

    class Meta(TuidMixin.Meta, TimeStampedMixin.Meta):
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        indexes = [Index(fields=["name"]), Index(fields=["nickname"])]

    if TYPE_CHECKING:
        pgh_event_model: PghEventModel
        totpdevice_set: QuerySet[TOTPDevice]
        otp_enabled: "datetime | None"  # annotated
        token_expires: "datetime | None"  # annotated
        pk: str

        # TODO: remove this
        async def acheck_password(self, raw_password: str) -> bool: ...

    def __str__(self):
        return f"{self.name} <{self.email}>"

    @property
    def username(self):
        return self.email

    @classmethod
    async def join(cls, *, name: str, email: str, password: str, agreements: list[str], callback_url: str):
        from apps.operation.models import PolicyAgreement, PolicyVersion

        mandatory_version_ids = await PolicyVersion.get_effective_mandatory_version_ids_to_join()
        if not set(str(id) for id in mandatory_version_ids).issubset(set(agreements)):
            raise ValueError(ErrorCode.MANDATORY_POLICY_NOT_ACCEPTED)

        try:
            user = await cls.objects.acreate(email=email, name=name, password=make_password(password))
        except IntegrityError:
            raise ValueError(ErrorCode.EMAIL_ALREADY_EXISTS)

        if agreements:
            await PolicyAgreement.agree_policies(user_id=user.id, agreements={str(id): True for id in agreements})

        await user.request_activation(callback_url=callback_url)
        return user

    def get_short_name(self):
        return self.name.split(" ")[0]

    async def token_login(self, *, password: str, request: HttpRequest, response: HttpResponse):
        if not self.is_active:
            raise ValueError(ErrorCode.USER_NOT_ACTIVE)
        if not await self.acheck_password(password):
            if await self.check_password_change_required(password):
                raise ValueError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
            raise ValueError(ErrorCode.INVALID_PASSWORD)

        # access token
        options = auth_cookie_options()
        max_age = settings.ACCESS_TOKEN_EXPIRE_SECONDS
        access_payload: TokenDict = {"sub": self.pk, "exp": int(time()) + max_age, "type": "access"}
        access_token = encode_token(access_payload)
        response.set_cookie(key="access_token", value=access_token, max_age=max_age, **options)

        # refresh token
        max_age = settings.REFRESH_TOKEN_EXPIRE_SECONDS
        refresh_payload: TokenDict = {"sub": self.pk, "exp": int(time()) + max_age, "type": "refresh"}
        refresh_token = encode_token(refresh_payload)
        response.set_cookie(key="refresh_token", value=refresh_token, max_age=max_age, **options)

        # save last login time
        now = timezone.now()
        expires = now + timedelta(seconds=max_age)

        token, _ = await Token.objects.aupdate_or_create(
            user=self,
            defaults={
                "token": refresh_token,
                "expires": expires,
                "ip_address": get_client_ip(request)[0],
                "user_agent": request.headers.get("user-agent"),  # by django-upgrade
            },
        )
        self.token_expires = token.expires

    @classmethod
    async def token_logout(cls, *, request: HttpRequest, response: HttpResponse):
        access_token = request.COOKIES.get(settings.ACCESS_TOKEN_NAME)
        refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_NAME)

        blacklisted_tokens: list[BlacklistedToken] = []
        for token in [access_token, refresh_token]:
            if not token:
                continue
            try:
                payload = decode_token(token)
                expires = datetime.fromtimestamp(payload["exp"], tz=dt_timezone.utc)
                blacklisted_tokens.append(BlacklistedToken(token=token, expires=expires))
            except InvalidTokenError:
                continue

        await BlacklistedToken.objects.abulk_create(
            blacklisted_tokens, update_conflicts=True, unique_fields=["token"], update_fields=["expires"]
        )

        response.delete_cookie(settings.ACCESS_TOKEN_NAME)
        response.delete_cookie(settings.REFRESH_TOKEN_NAME)

    @classmethod
    async def get_user(cls, *, is_active: bool | None = None, annotate: bool = False, **kwargs):
        manager = (
            cls.objects.annotate(
                otp_enabled=Subquery(
                    TOTPDevice.objects
                    .filter(user_id=OuterRef("pk"), confirmed=True)
                    .order_by("-created_at")
                    .values("created_at")[:1]
                ),
                token_expires=F("token__expires"),
            )
            if annotate
            else cls.objects
        )

        # Design Decision: Clarity over Security for non-technical users
        try:
            user = await manager.aget(**kwargs)
            if is_active is True and not user.is_active:
                raise ValueError(ErrorCode.USER_NOT_ACTIVE)
            if is_active is False and user.is_active:
                raise ValueError(ErrorCode.USER_ALREADY_ACTIVE)
            return user
        except cls.DoesNotExist:
            raise ValueError(ErrorCode.USER_NOT_FOUND)

    async def activate(self):
        self.is_active = True
        await self.asave()

    async def change_password(self, *, password: str):
        self.set_password(password)
        await self.asave()

    async def request_activation(self, *, callback_url: str):
        if self.is_active:
            raise ValueError(ErrorCode.USER_ALREADY_ACTIVE)

        await self._send_verification_email(
            template_name="activation",
            title=_("Account Activation"),
            expiry=settings.ACTIVATION_TOKEN_EXPIRY,
            user_id=self.pk,
            name=self.name,
            recipient_email=self.email,
            callback_url=callback_url,
        )

    async def request_email_change(self, *, callback_url: str, password: str, new_email: str):
        if not await self.acheck_password(password):
            raise ValueError(ErrorCode.INVALID_PASSWORD)
        if self.email == new_email:
            raise ValueError(ErrorCode.SAME_EMAIL)
        if await self._meta.model.objects.filter(email=new_email).aexists():
            raise ValueError(ErrorCode.EMAIL_ALREADY_EXISTS)

        await self._send_verification_email(
            template_name="email_change",
            title=_("Email Change"),
            expiry=settings.EMAIL_CHANGE_TOKEN_EXPIRY,
            user_id=self.pk,
            name=self.name,
            recipient_email=new_email,
            callback_url=callback_url,
        )

    async def request_password_change(self, callback_url: str):
        await self._send_verification_email(
            template_name="password_change",
            title=_("Password Change"),
            expiry=settings.PASSWORD_CHANGE_TOKEN_EXPIRY,
            user_id=self.pk,
            name=self.name,
            recipient_email=self.email,
            callback_url=callback_url,
        )

    @classmethod
    async def _send_verification_email(
        cls,
        template_name: AuthTokenType,
        title: str,
        expiry: int,
        user_id: str,
        name: str,
        recipient_email: str,
        callback_url: str,
    ):
        payload: TokenDict = {"sub": user_id, "exp": int(time()) + expiry, "type": template_name}

        if template_name == "email_change":
            payload["to"] = recipient_email

        callback_url = f"{callback_url}?token={encode_token(payload)}"
        expiry_hours = expiry // 60 // 60

        context = {"name": name, "callback_url": callback_url, "expiry_hours": expiry_hours}
        template = load_template(template_name)
        body = template.render(context).strip()

        await sync_to_async(send_mail)(
            subject=title,
            message="",
            html_message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )

    async def update_user(
        self, *, email: str | None = None, preferences: dict[str, bool | str | int] | None = None, **data: object
    ):
        if preferences:
            self.preferences = {**self.preferences, **preferences}
        if email:
            if email == self.email:
                raise ValueError(ErrorCode.SAME_EMAIL)
            if await self._meta.model.objects.filter(email=email).exclude(email=self.email).aexists():
                raise ValueError(ErrorCode.EMAIL_ALREADY_EXISTS)
            self.email = email
        for field, value in data.items():
            setattr(self, field, value)
        await self.asave()
        return self

    async def check_password_change_required(self, password: str):
        if self.password:
            return False
        temp_passwords = await TempPassword.objects.filter(user=self, expires__gt=timezone.now()).afirst()
        if not temp_passwords:
            return False
        self.password = temp_passwords.password
        return await self.acheck_password(password)

    async def save_reaction(
        self, *, target_id: str, app_label: str, model: str, kind: Literal["like", "flag", "bookmark"] | None
    ):
        target_type = await sync_to_async(ContentType.objects.get_by_natural_key)(app_label, model)
        if not kind:
            await Reaction.objects.filter(user=self, target_type=target_type, target_id=target_id).adelete()
            return

        await Reaction.objects.aupdate_or_create(
            user=self, target_type=target_type, target_id=target_id, defaults={"modified": timezone.now(), "kind": kind}
        )

    async def setup_otp(self):
        if await TOTPDevice.objects.filter(user=self, confirmed=True).aexists():
            raise ValueError(ErrorCode.OTP_ALREADY_ENABLED)
        await TOTPDevice.objects.filter(user=self, confirmed=False).adelete()
        await StaticDevice.objects.filter(user=self, confirmed=False).adelete()

        device = await TOTPDevice.objects.acreate(user=self, name="default", confirmed=False)
        uri = device.config_url
        qr = qrcode.QRCode(version=1, box_size=10, border=1)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, kind="PNG")
        buffer.seek(0)
        qr_code = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"

        backup_codes = []
        static_device = await StaticDevice.objects.acreate(user=self, name="backup", confirmed=False)

        static_tokens = []
        for __ in range(10):
            token = StaticToken.random_token()
            static_tokens.append(StaticToken(device=static_device, token=token))
            backup_codes.append(token)
        await StaticToken.objects.abulk_create(static_tokens)

        return SetupOtpDict(qr_code=qr_code, backup_codes=backup_codes, secret_key=device.key)

    async def _log_otp_verification(
        self,
        *,
        code: str,
        fingerprint: str,
        consumer_type: ContentType,
        consumer_id: str,
        device_type: str,
        success: bool,
    ):
        now = timezone.now()
        await OtpLog.objects.acreate(
            created=now,
            modified=now,
            code=code,
            fingerprint=fingerprint,
            success=success,
            device_type=device_type,
            consumer_type=consumer_type,
            consumer_id=consumer_id,
            user=self,
        )

    async def complete_otp_setup(self, *, code: str, fingerprint: str):
        device = await TOTPDevice.objects.filter(user=self, confirmed=False).afirst()
        if not device:
            raise ValueError(ErrorCode.INVALID_OTP_CODE)

        success = await sync_to_async(device.verify_token)(code)
        await self._log_otp_verification(
            code=code,
            fingerprint=fingerprint,
            consumer_type=await sync_to_async(ContentType.objects.get_for_model)(self),
            consumer_id=self.pk,
            device_type="totp",
            success=success,
        )

        if not success:
            raise ValueError(ErrorCode.INVALID_OTP_CODE)

        device.confirmed = True
        device.drift = 0
        device.last_t = -1  # exceptionally allow reuse
        await device.asave()

        static_device = await StaticDevice.objects.filter(user=self, confirmed=False).afirst()
        if static_device:
            static_device.confirmed = True
            await static_device.asave()

        return device

    async def verify_otp(self, *, token: str, code: str, fingerprint: str):
        try:
            consumer_data: OtpTokenDict = loads(token, max_age=settings.OTP_VERIFICATION_EXPIRY)
        except SignatureExpired:
            raise ValueError(ErrorCode.OTP_TOKEN_EXPIRED)
        except BadSignature:
            raise ValueError(ErrorCode.INVALID_OTP_TOKEN)

        if consumer_data["user_id"] != self.id:
            raise ValueError(ErrorCode.INVALID_OTP_TOKEN)

        try:
            app_label, model = consumer_data["app_label"], consumer_data["model"]
            consumer_type = await sync_to_async(ContentType.objects.get_by_natural_key)(app_label, model)
        except ObjectDoesNotExist, LookupError:
            raise ValueError(ErrorCode.INVALID_OTP_CONSUMER)

        totp_devices = [device async for device in TOTPDevice.objects.filter(user=self, confirmed=True)]
        static_devices = [device async for device in StaticDevice.objects.filter(user=self, confirmed=True)]

        if not totp_devices and not static_devices:
            raise ValueError(ErrorCode.OTP_NOT_SETUP)

        success = False
        device_type = None

        for device in totp_devices:
            if await sync_to_async(device.verify_token)(code):
                await sync_to_async(device.set_last_used_timestamp)()
                await device.asave()
                success = True
                device_type = "totp"
                break

        if not success:
            for static_device in static_devices:
                if await sync_to_async(static_device.verify_token)(code):
                    success = True
                    device_type = "static"
                    break

        await self._log_otp_verification(
            code=code,
            fingerprint=fingerprint,
            consumer_type=consumer_type,
            consumer_id=consumer_data["consumer_id"],
            device_type=device_type or "none",
            success=success,
        )

        if not success:
            raise ValueError(ErrorCode.INVALID_OTP_CODE)

    async def reset_otp(self):
        await TOTPDevice.objects.filter(user=self).adelete()
        await StaticDevice.objects.filter(user=self).adelete()

    @staticmethod
    def decode_auth_token(token: str, expected_type: AuthTokenType) -> TokenDict:
        try:
            payload = decode_token(token)
            if payload["type"] != expected_type:
                raise InvalidTokenError()
            if expected_type == "email_change":
                if not payload.get("to"):
                    raise ValueError(ErrorCode.INVALID_TOKEN)
        except InvalidTokenError:
            raise ValueError(ErrorCode.INVALID_TOKEN)

        return payload


@pghistory.track()
class TempPassword(Model):
    user = OneToOneField(User, CASCADE, verbose_name=_("User"))
    password = CharField(_("Password"), max_length=128)
    expires = DateTimeField(_("Expires"))

    class Meta:
        verbose_name = _("Temporary Password")
        verbose_name_plural = _("Temporary Passwords")


@pghistory.track()
class Reaction(TimeStampedMixin):
    class ReactionChoices(TextChoices):
        BOOKMARK = "bookmark", _("Bookmark")
        LIKE = "like", _("Like")
        FLAG = "flag", _("Flag")

    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    kind = CharField(_("Kind"), max_length=10, choices=ReactionChoices)
    target_type = ForeignKey(ContentType, CASCADE, verbose_name=_("Target Type"))
    target_id = CharField(_("Target ID"), max_length=36)
    target = GenericForeignKey("target_type", "target_id")

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Reaction")
        verbose_name_plural = _("Reactions")
        constraints = [
            UniqueConstraint(fields=["user", "target_type", "target_id"], name="account_reaction_us_kaid_taty_uniq")
        ]

    if TYPE_CHECKING:
        pk: int


@pghistory.track()
class Token(TimeStampedMixin):
    user = OneToOneField(User, CASCADE, verbose_name=_("User"))
    token = CharField(_("Token"), max_length=500, db_index=True)
    expires = DateTimeField(_("Expires"))
    ip_address = GenericIPAddressField(_("IP Address"), null=True, blank=True)
    user_agent = TextField(_("User Agent"), null=True, blank=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Token")
        verbose_name_plural = _("Tokens")


@pghistory.track()
class BlacklistedToken(Model):
    token = CharField(_("Token"), max_length=500, unique=True)
    expires = DateTimeField(_("Expires"))

    class Meta:
        verbose_name = _("Blacklisted Token")
        verbose_name_plural = _("Blacklisted Tokens")


@pghistory.track()
class OtpLog(TimeStampedMixin):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    code = CharField(_("Code"), max_length=30)
    success = BooleanField(_("Success"), default=False)
    fingerprint = CharField(_("Fingerprint"), max_length=255)
    device_type = CharField(_("Device Type"), max_length=50, default="totp")

    consumer_type = ForeignKey(ContentType, CASCADE, verbose_name=_("Consumer Type"))
    consumer_id = CharField(_("Consumer ID"), max_length=36)
    consumer = GenericForeignKey("consumer_type", "consumer_id")

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("OTP Log")
        verbose_name_plural = _("OTP Logs")
        indexes = [Index(fields=["consumer_type", "consumer_id"], name="account_otplog_coty_coid_idx")]

    @classmethod
    async def check_otp_verification(cls, *, user_id: str, consumer: Model):
        consumer_type = await sync_to_async(ContentType.objects.get_for_model)(consumer)
        return await cls.objects.filter(
            user_id=user_id,
            consumer_type=consumer_type,
            consumer_id=consumer.pk,
            success=True,
            created__gte=timezone.now() - timedelta(seconds=settings.OTP_VERIFICATION_EXPIRY),
        ).aexists()
