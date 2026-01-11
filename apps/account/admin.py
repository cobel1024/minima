import secrets
import string
from datetime import timedelta

from django import forms
from django.contrib import admin
from django.contrib.auth.hashers import make_password
from django.http.request import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext as _
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from unfold.contrib.filters.admin import BooleanRadioFilter
from unfold.decorators import action
from unfold.widgets import UnfoldAdminSelectWidget

from apps.account.models import BlacklistedToken, OtpLog, Reaction, TempPassword, Token, User
from apps.common.admin import (
    HiddenModelAdmin,
    ModelAdmin,
    ReadOnlyHiddenModelAdmin,
    ReadOnlyTabularInline,
    TabularInline,
)


@admin.register(User)
class UserAdmin(ModelAdmin[User]):
    # form = UserChangeForm
    # add_form = UserCreationForm

    list_filter_submit = True
    exclude = ("password", "groups", "user_permissions")

    class ReactionInline(TabularInline[Reaction]):
        model = Reaction

    class UserEventInline(ReadOnlyTabularInline[User.pgh_event_model]):
        model = User.pgh_event_model
        exclude = ("pgh_context",)
        verbose_name = _("Change History")
        verbose_name_plural = _("Change Histories")

    class TokenInline(ReadOnlyTabularInline[Token]):
        model = Token
        verbose_name = _("Login Token")
        verbose_name_plural = _("Login Tokens")

    class OtpLogInline(ReadOnlyTabularInline[OtpLog]):
        model = OtpLog
        verbose_name = _("OTP Log")
        verbose_name_plural = _("OTP Logs")

    inlines = (UserEventInline, TokenInline, OtpLogInline, ReactionInline)

    list_filter = (("is_staff", BooleanRadioFilter), ("is_superuser", BooleanRadioFilter))

    actions_submit_line = ["create_temp_password"]

    @action(description=_("Create temporary password"), permissions=["create_temp_password"])
    def create_temp_password(self, request: HttpRequest, obj: User):
        expiry_hours = 2
        alphabet = string.ascii_letters + string.digits
        plain_password = "".join(secrets.choice(alphabet) for _ in range(8))

        TempPassword.objects.update_or_create(
            user=obj,
            defaults={
                "password": make_password(plain_password),
                "expires": timezone.now() + timedelta(hours=expiry_hours),
            },
        )

        # remove existing password
        obj.password = ""
        obj.save()

        self.message_user(
            request,
            _("Temporary password created for {user}: {password}. Expires in {hours} hours.").format(
                user=obj.name, password=plain_password, hours=expiry_hours
            ),
        )

    def has_create_temp_password_permission(self, request, object_id):
        return True

    def get_form(self, request: HttpRequest, obj: User | None = None, change: bool = False, **kwargs: object):
        form = super().get_form(request, obj, change=change, **kwargs)
        base_fields = getattr(form, "base_fields", {})
        if "language" in base_fields:
            base_fields["language"] = forms.ChoiceField(
                choices=[("", ""), ("en", _("English")), ("ko", _("Korean"))],
                required=False,
                widget=UnfoldAdminSelectWidget(),
            )
        return form


@admin.register(Reaction)
class ReactionAdmin(HiddenModelAdmin[Reaction]):
    pass


@admin.register(Token)
class TokenAdmin(ReadOnlyHiddenModelAdmin[Token]):
    pass


@admin.register(BlacklistedToken)
class BlacklistedTokenAdmin(HiddenModelAdmin[BlacklistedToken]):
    pass


@admin.register(OtpLog)
class OtpLogAdmin(ReadOnlyHiddenModelAdmin[OtpLog]):
    pass


@admin.register(User.pgh_event_model)
class UserEventAdmin(ReadOnlyHiddenModelAdmin[User.pgh_event_model]):
    pass


# unregister django otp models
admin.site.unregister(TOTPDevice)
admin.site.unregister(StaticDevice)
