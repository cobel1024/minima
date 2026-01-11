from typing import Annotated

from django.conf import settings
from django.http import HttpResponse
from ninja.files import UploadedFile
from ninja.pagination import paginate
from ninja.params import functions
from ninja.router import Router

from apps.account.api.schema import (
    AccountActivateSchema,
    ApplyEmailChangeSchema,
    ApplyPasswordChangeSchema,
    JoinSchema,
    LoginSchema,
    OtpSetupCompleteSchema,
    OtpSetupSchema,
    OtpVerifySchema,
    ReactionSaveSchema,
    ReactionSchema,
    RequestactivationSchema,
    RequestEmailChangeSchema,
    RequestPasswordChangeSchema,
    TOTPDeviceSchema,
    UserSchema,
    UserUpdateSchema,
)
from apps.account.models import Reaction, User
from apps.common.error import ErrorCode
from apps.common.util import HttpRequest, Pagination, no_auth_required

router = Router(by_alias=True)


@router.post("/login", response=UserSchema, auth=no_auth_required)
async def login(request: HttpRequest, response: HttpResponse, data: LoginSchema):
    user = await User.get_user(email=data.email, is_active=True, annotate=True)
    await user.token_login(password=data.password, request=request, response=response)
    return user


@router.post("/join", auth=no_auth_required)
async def join(request: HttpRequest, data: JoinSchema):
    await User.join(
        name=data.name,
        email=data.email,
        password=data.password,
        agreements=data.agreements,
        callback_url=str(data.callback_url),
    )


@router.post("/requestactivation", auth=no_auth_required)
async def request_activation(request: HttpRequest, data: RequestactivationSchema):
    user = await User.get_user(email=data.email, is_active=False)
    await user.request_activation(callback_url=str(data.callback_url))


@router.post("/activate", auth=no_auth_required)
async def activate(request: HttpRequest, data: AccountActivateSchema):
    payload = User.decode_auth_token(data.token, "activation")
    user = await User.get_user(id=payload["sub"], is_active=False)
    await user.activate()


@router.get("/me", response=UserSchema)
async def get_me(request: HttpRequest):
    return await User.get_user(id=request.auth, is_active=True, annotate=True)


@router.post("/me", response=UserSchema)
async def update_me(request: HttpRequest, data: UserUpdateSchema):
    user = await User.get_user(id=request.auth, is_active=True, annotate=True)
    update_data = data.model_dump(exclude_unset=True, exclude={"delete_avatar"})
    return await user.update_user(**update_data)


@router.post("/me/avatar", response=str | None)
async def upload_avatar(
    request: HttpRequest,
    avatar_file: Annotated[
        UploadedFile | None,
        functions.File(None, description=f"Max size: {settings.AVATAR_MAX_SIZE_MB}MB", alias="avatarFile"),
    ],
):
    if avatar_file:
        if avatar_file.size > settings.AVATAR_MAX_SIZE_MB * 1024 * 1024:
            raise ValueError(ErrorCode.FILE_TOO_LARGE)
        if not avatar_file.content_type or not avatar_file.content_type.startswith("image/"):
            raise ValueError(ErrorCode.INVALID_FILE_TYPE)

    user = await User.get_user(id=request.auth, is_active=True)
    await user.update_user(avatar=avatar_file)
    return user.avatar


@router.post("/requestemailchange")
async def request_email_change(request: HttpRequest, data: RequestEmailChangeSchema):
    user = await User.get_user(id=request.auth, is_active=True)
    await user.request_email_change(
        password=data.password, new_email=data.new_email, callback_url=str(data.callback_url)
    )


@router.post("/applyemailchange")
async def apply_email_change(request: HttpRequest, data: ApplyEmailChangeSchema, response: HttpResponse):
    payload = User.decode_auth_token(data.token, "email_change")
    user = await User.get_user(id=request.auth, is_active=True)
    if user.id != payload["sub"]:
        raise ValueError(ErrorCode.INVALID_TOKEN)
    await user.update_user(email=payload["to"])
    await user.token_logout(request=request, response=response)


@router.post("/requestpasswordchange", auth=no_auth_required)
async def request_password_change(request: HttpRequest, data: RequestPasswordChangeSchema):
    user = await User.get_user(email=data.email, is_active=True)
    await user.request_password_change(callback_url=str(data.callback_url))


@router.post("/applypasswordchange", auth=no_auth_required)
async def apply_password_change(request: HttpRequest, data: ApplyPasswordChangeSchema):
    payload = User.decode_auth_token(data.token, "password_change")
    user = await User.get_user(id=payload["sub"], is_active=True)
    await user.change_password(password=data.password)


@router.post("/logout")
async def logout(request: HttpRequest, response: HttpResponse):
    await User.token_logout(request=request, response=response)


@router.get("/reaction", response=list[ReactionSchema])
@paginate(Pagination)
async def get_reactions(request: HttpRequest):
    return Reaction.objects.select_related("target_type").filter(user_id=request.auth).order_by("-id")


@router.post("/reaction")
async def save_reaction(request: HttpRequest, data: ReactionSaveSchema):
    user = await User.get_user(id=request.auth, is_active=True)
    await user.save_reaction(**data.model_dump())


@router.post("/otp/setup", response=OtpSetupSchema)
async def setup_otp(request: HttpRequest):
    user = await User.get_user(id=request.auth, is_active=True)
    return await user.setup_otp()


@router.post("/otp/setup/complete", response=TOTPDeviceSchema)
async def complete_otp_setup(request: HttpRequest, data: OtpSetupCompleteSchema):
    user = await User.get_user(id=request.auth, is_active=True)
    return await user.complete_otp_setup(code=data.code, fingerprint=data.fingerprint)


@router.post("/otp/verify")
async def verify_otp(request: HttpRequest, data: OtpVerifySchema):
    user = await User.get_user(id=request.auth, is_active=True)
    await user.verify_otp(**data.model_dump())


@router.post("/otp/reset")
async def reset_otp(request: HttpRequest):
    user = await User.get_user(id=request.auth, is_active=True)
    await user.reset_otp()
