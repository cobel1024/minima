import hashlib
import os
import re
from typing import TYPE_CHECKING, Sequence

import pghistory
from asgiref.sync import sync_to_async
from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.files import File
from django.db.models import (
    CASCADE,
    SET_NULL,
    BooleanField,
    CharField,
    Count,
    DateTimeField,
    EmailField,
    F,
    FileField,
    FloatField,
    ForeignKey,
    ImageField,
    Index,
    IntegerField,
    JSONField,
    ManyToManyField,
    Model,
    OuterRef,
    PositiveIntegerField,
    PositiveSmallIntegerField,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    TextChoices,
    TextField,
    UniqueConstraint,
    Window,
)
from django.db.models.functions.window import RowNumber
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from openpyxl.packaging.manifest import mimetypes
from taggit.managers import TaggableManager
from taggit.models import CommonGenericTaggedItemBase, TagBase, TaggedItemBase
from treebeard.mp_tree import MP_Node

from apps.common.error import ErrorCode
from apps.common.models import BooleanNowField, OrderableMixin, SoftDeleteMixin, TimeStampedMixin
from apps.operation.trigger import thread_comment_stats

User = get_user_model()


@pghistory.track()
class Category(MP_Node):
    name = CharField(_("Name"), max_length=100)
    ancestors = ArrayField(CharField(_("Ancestors"), max_length=200), editable=False)

    class Meta(MP_Node.Meta):
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")

    if TYPE_CHECKING:
        pk: int

    def __str__(self):
        return " / ".join(self.ancestors + [self.name])

    def save(self, *args, **kwargs):
        parent = self.get_parent()
        self.ancestors = parent.ancestors + [parent.name] if parent else []
        return super().save(*args, **kwargs)


@pghistory.track()
class Tag(TagBase):
    class Meta(TagBase.Meta):
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")


@pghistory.track()
class TaggedItem(CommonGenericTaggedItemBase, TaggedItemBase):
    object_id = CharField(_("Object ID"), max_length=36)
    tag = ForeignKey(Tag, CASCADE, related_name="%(app_label)s_%(class)s_items", verbose_name=_("Tag"))

    class Meta(CommonGenericTaggedItemBase.Meta, TaggedItemBase.Meta):
        verbose_name = _("Tagged Item")
        verbose_name_plural = _("Tagged Items")
        indexes = [Index(fields=["content_type", "object_id"]), Index(fields=["object_id"])]
        constraints = [
            UniqueConstraint(fields=["tag", "content_type", "object_id"], name="operation_taggeditem_ta_coty_obid_uniq")
        ]


class TaggableMixin(Model):
    tag_set = TaggableManager(through=TaggedItem, blank=True)

    class Meta:
        abstract = True

    def set_tags(self, tag_names: list[str] | None):
        if tag_names:
            self.tag_set.set(tag_names)
        else:
            self.tag_set.clear()


@pghistory.track()
class Announcement(TimeStampedMixin):
    title = CharField(_("Title"), max_length=255, unique=True)
    body = TextField(_("Body"))
    public = BooleanField(_("Public"), default=True)
    pinned = BooleanField(_("Pinned"), default=False)
    reads = ManyToManyField(User, blank=True, through="AnnouncementRead", verbose_name=_("Reads"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Announcement")
        verbose_name_plural = _("Announcements")

    if TYPE_CHECKING:
        pk: int

    def __str__(self):
        return self.title

    @classmethod
    def get_announcements(cls, user_id: str):
        return (
            cls.objects
            .annotate(
                read=Subquery(
                    AnnouncementRead.objects.filter(announcement_id=OuterRef("pk"), user_id=user_id).values("read")[:1]
                )
            )
            .filter(public=True)
            .order_by("-pinned", "-id")
        )


@pghistory.track()
class AnnouncementRead(Model):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    announcement = ForeignKey(Announcement, CASCADE, verbose_name=_("Announcement"))
    read = DateTimeField(_("Read at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Announcement Read")
        verbose_name_plural = _("Announcement Reads")
        constraints = [UniqueConstraint(fields=["user", "announcement"], name="operation_announcementread_us_an_uniq")]


@pghistory.track()
class Instructor(TimeStampedMixin):
    name = CharField(_("Name"), max_length=50)
    email = EmailField(_("Email"), unique=True)
    about = TextField(_("About"))
    bio = ArrayField(CharField(max_length=200), verbose_name=_("Bio"))
    avatar = ImageField(_("Avatar"), null=True, blank=True)
    active = BooleanField(_("Active"), default=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Instructor")
        verbose_name_plural = _("Instructors")
        indexes = [Index(fields=["name"])]

    if TYPE_CHECKING:
        pk: int

    def __str__(self):
        return self.name


@pghistory.track()
class HonorCode(TimeStampedMixin):
    title = CharField(max_length=255, verbose_name=_("Title"), unique=True)
    code = TextField(_("Code"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Honor Code")
        verbose_name_plural = _("Honor Codes")

    def __str__(self):
        return self.title


@pghistory.track()
class FAQ(Model):
    name = CharField(_("Name"), max_length=255, unique=True)
    description = TextField(_("Description"), blank=True, default="")

    class Meta:
        verbose_name = _("FAQ")
        verbose_name_plural = _("FAQs")

    if TYPE_CHECKING:
        faqitem_set: "QuerySet[FAQItem]"

    def __str__(self):
        return self.name


@pghistory.track()
class FAQItem(OrderableMixin, TimeStampedMixin):
    faq = ForeignKey(FAQ, CASCADE, verbose_name=_("FAQ"))
    question = CharField(_("Question"), max_length=255)
    answer = TextField(_("Answer"))
    active = BooleanField(_("Active"), default=True)
    ordering_group = ("faq",)

    class Meta(OrderableMixin.Meta, TimeStampedMixin.Meta):
        verbose_name = _("FAQ")
        verbose_name_plural = _("FAQs")
        constraints = [UniqueConstraint(fields=["faq", "question"], name="operation_faqitem_fa_qu_uniq")]


@pghistory.track()
class Attachment(SoftDeleteMixin, TimeStampedMixin):
    file = FileField(_("File"), max_length=255, unique=True)
    size = IntegerField(_("Size"), null=True, blank=True)
    mime_type = CharField(_("Mime Type"), max_length=100)
    hash = CharField(max_length=64, db_index=True)
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"))
    deleted = DateTimeField(_("Deleted"), null=True, blank=True)

    class Meta(SoftDeleteMixin.Meta, TimeStampedMixin.Meta):
        verbose_name = _("Attachment")
        verbose_name_plural = _("Attachments")
        constraints = [UniqueConstraint(fields=["hash", "owner"], name="operation_attachment_ha_own_uniq")]

    def fill_metadata(self):
        self.size = self.file.size
        self.mime_type = mimetypes.guess_type(self.file.name)[0] or ""
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.file.name.encode())
        for chunk in self.file.chunks():
            hasher.update(chunk)
        return hasher.hexdigest()


ATTACHMENT_MAX_COUNT = settings.ATTACHMENT_MAX_COUNT
ATTACHMENT_MAX_SIZE = settings.ATTACHMENT_MAX_SIZE_MB * 1024 * 1024


class AttachmentMixin(Model):
    attachments = ManyToManyField(Attachment, verbose_name=_("Attachments"), blank=True, related_name="+")

    class Meta:
        abstract = True

    def restore_filename(self, filename: str) -> str:
        name, ext = os.path.splitext(filename)
        parts = name.rsplit(".", 1)
        if len(parts) == 2:
            return f"{parts[0]}{ext}"
        return filename

    def _extract_used_filenames(self, content: str) -> set[str]:
        used_filenames = set()

        img_matches = re.findall(r'<img[^>]*alt="([^"]*)"[^>]*>', content)
        used_filenames.update(img_matches)

        link_matches = re.findall(r'<a[^>]*download="([^"]*)"[^>]*>', content)
        used_filenames.update(link_matches)

        return used_filenames

    async def update_attachments(self, *, files: Sequence[File] | None, owner_id: str, content: str):
        used_filenames = self._extract_used_filenames(content)
        attachments_to_keep: list[Attachment] = []
        seen_hashes = set()

        existing_attachments = []
        if self.pk:
            async for a in self.attachments.all():
                existing_attachments.append(a)
                if self.restore_filename(a.file.name) in used_filenames:
                    attachments_to_keep.append(a)
                    seen_hashes.add((a.hash, owner_id))

        new_attachments_to_create: list[Attachment] = []
        for f in files or []:
            attachment = Attachment(file=f, owner_id=owner_id, deleted=None)
            attachment.fill_metadata()
            hash_key = (attachment.hash, owner_id)

            if hash_key not in seen_hashes and f.name in used_filenames:
                new_attachments_to_create.append(attachment)
                seen_hashes.add(hash_key)

        if new_attachments_to_create:
            created = await Attachment.objects.abulk_create(
                new_attachments_to_create,
                update_conflicts=True,
                update_fields=["deleted"],
                unique_fields=["hash", "owner"],
            )
            attachments_to_keep.extend(created)

        existing_ids = set(a.id for a in existing_attachments)
        new_ids = set(a.pk for a in attachments_to_keep)
        if existing_ids != new_ids:
            await self.attachments.aset(attachments_to_keep)

        if hasattr(self, "_prefetched_objects_cache"):
            self._prefetched_objects_cache["attachments"] = attachments_to_keep
        else:
            self._prefetched_objects_cache = {"attachments": attachments_to_keep}

        return attachments_to_keep

    def update_attachment_urls(self, *, content: str):
        attachments = self.attachments.all()
        if not attachments:
            return content

        for attachment in attachments:
            original_name = self.restore_filename(attachment.file.name)
            presigned_url = attachment.file.storage.url(attachment.file.name)
            escaped_name = re.escape(original_name)

            img_pattern = f'<img[^>]*alt="{escaped_name}"[^>]*>'

            def replace_src(match):
                img_tag = match.group(0)
                return re.sub(r'src="[^"]*"', f'src="{presigned_url}"', img_tag)

            content = re.sub(img_pattern, replace_src, content)

            link_pattern = f'<a[^>]*download="{escaped_name}"[^>]*>'

            def replace_href(match):
                a_tag = match.group(0)
                return re.sub(r'href="[^"]*"', f'href="{presigned_url}"', a_tag)

            content = re.sub(link_pattern, replace_href, content)

        return content

    @staticmethod
    def validate_files(
        files: Sequence[File], *, max_count: int = ATTACHMENT_MAX_COUNT, max_size: int = ATTACHMENT_MAX_SIZE
    ):
        if len(files) > max_count:
            raise ValueError(ErrorCode.ATTACHMENT_TOO_MANY)
        for f in files or []:
            if f.size > max_size:
                raise ValueError(ErrorCode.ATTACHMENT_TOO_LARGE)


@pghistory.track()
class Inquiry(TimeStampedMixin, AttachmentMixin):
    title = CharField(_("Title"), max_length=255)
    question = TextField(_("Question"))
    writer = ForeignKey(User, CASCADE, verbose_name=_("Writer"))
    content_type = ForeignKey(ContentType, CASCADE, verbose_name=_("Content Type"))
    content_id = CharField(_("Content ID"), max_length=36, db_index=True)
    content = GenericForeignKey("content_type", "content_id")

    class Meta(TimeStampedMixin.Meta, AttachmentMixin.Meta):
        verbose_name = _("Inquiry")
        verbose_name_plural = _("Inquiries")
        indexes = [Index(fields=["content_type", "content_id"])]

    if TYPE_CHECKING:
        solved: bool  # annotated
        inquiryresponse_set: "QuerySet[InquiryResponse]"
        response_count: int  # annotated

    @property
    def responses(self):
        return self.inquiryresponse_set.all()

    @property
    def cleaned_question(self):
        return self.update_attachment_urls(content=self.question)

    @classmethod
    async def create(
        cls,
        *,
        title: str,
        question: str,
        app_label: str,
        model: str,
        content_id: int,
        writer_id: str,
        files: Sequence[File] | None,
    ):
        content_type = await sync_to_async(ContentType.objects.get_by_natural_key)(app_label, model)
        inquiry = await cls.objects.acreate(
            title=title, question=question, writer_id=writer_id, content_type=content_type, content_id=content_id
        )
        await inquiry.update_attachments(files=files, owner_id=writer_id, content=inquiry.question)
        return inquiry

    @classmethod
    async def update(cls, *, title: str, question: str, writer_id: str, id: int, files: Sequence[File] | None):
        inquiry = (
            await cls.objects
            .select_related("writer")
            .annotate(response_count=Count("inquiryresponse"))
            .aget(id=id, writer_id=writer_id)
        )

        if inquiry.response_count > 0:
            raise ValueError(ErrorCode.RESPONSE_EXISTS)

        inquiry.title = title
        inquiry.question = question
        await inquiry.asave()
        await inquiry.update_attachments(files=files, owner_id=writer_id, content=inquiry.question)
        return inquiry


@pghistory.track()
class InquiryResponse(TimeStampedMixin):
    inquiry = ForeignKey(Inquiry, CASCADE, verbose_name=_("Inquiry"))
    answer = TextField(_("Answer"))
    writer = ForeignKey(User, CASCADE, verbose_name=_("Writer"))
    solved = BooleanNowField(_("Solved"), null=True, blank=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Inquiry Response")
        verbose_name_plural = _("Inquiry Responses")
        constraints = [
            UniqueConstraint(
                fields=["inquiry"], condition=Q(solved__isnull=False), name="operation_inquiryresponse_in_sol_uniq"
            )
        ]


@pghistory.track()
class Appeal(TimeStampedMixin, AttachmentMixin):
    learner = ForeignKey(User, CASCADE, verbose_name=_("Learner"), related_name="+")
    explanation = TextField(_("Explanation"))
    review = TextField(_("Review"), blank=True, default="")
    closed = BooleanNowField(_("Closed"), null=True, blank=True)

    limit_choices_to = {"model__in": ["question"]}
    question_type = ForeignKey(ContentType, CASCADE, verbose_name=_("Question Type"), limit_choices_to=limit_choices_to)
    question_id = IntegerField(_("Question ID"))
    question = GenericForeignKey("question_type", "question_id")

    class Meta(TimeStampedMixin.Meta, AttachmentMixin.Meta):
        verbose_name = _("Grade Appeal")
        verbose_name_plural = _("Grade Appeals")
        constraints = [
            UniqueConstraint(
                fields=["question_type", "question_id", "learner"], name="operation_appeal_quid_quty_le_uniq"
            )
        ]

    @property
    def cleaned_explanation(self):
        return self.update_attachment_urls(content=self.explanation)

    @classmethod
    async def create(
        cls,
        *,
        learner_id: str,
        question_id: int,
        app_label: str,
        model: str,
        explanation: str,
        files: Sequence[File] | None,
    ):
        question_type = await sync_to_async(ContentType.objects.get_by_natural_key)(app_label, model)
        appeal, created = await cls.objects.aget_or_create(
            learner_id=learner_id,
            question_id=question_id,
            question_type=question_type,
            defaults={"explanation": explanation},
        )

        if not created:
            raise ValueError(ErrorCode.ALREADY_EXISTS)

        await appeal.update_attachments(files=files, owner_id=learner_id, content=appeal.explanation)
        return appeal


@pghistory.track(exclude=["body"])
class Message(TimeStampedMixin):
    class ChannelChoices(TextChoices):
        EMAIL = "email", _("Email")
        TEXT = "text", _("Text")
        FCM = "fcm", _("FCM")

    channel = CharField(_("Channel"), max_length=20, choices=ChannelChoices)
    group = CharField(_("Group"), blank=True, default="", max_length=255)
    title = CharField(_("Title"), max_length=255)
    body = TextField(_("Body"))
    data = JSONField(_("Data"), default=dict, blank=True)
    recipients = ArrayField(CharField(max_length=255), verbose_name=_("Recipient Addresses"))
    user = ForeignKey(User, SET_NULL, null=True, blank=True, verbose_name=_("User"))
    reserved = DateTimeField(_("Reserved"), null=True, blank=True)
    sent = DateTimeField(_("Sent"), null=True, blank=True)
    read = DateTimeField(_("Read"), null=True, blank=True)
    error = TextField(_("Error"), blank=True, default="")

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")
        indexes = [Index(fields=["group"]), Index(fields=["reserved"])]


@pghistory.track()
class Policy(TimeStampedMixin):
    class KindChoices(TextChoices):
        TERMS_OF_SERVICE = "terms_of_service", _("Terms of Service")
        PRIVACY_POLICY = "privacy_policy", _("Privacy Policy")
        COOKIE_POLICY = "cookie_policy", _("Cookie Policy")
        MARKETING_POLICY = "marketing_policy", _("Marketing Policy")
        DATA_RETENTION_POLICY = "data_retention_policy", _("Data Retention Policy")

    kind = CharField(_("Kind"), max_length=30, choices=KindChoices, unique=True)
    title = CharField(_("Title"), max_length=255)
    description = TextField(_("Description"), blank=True, default="")
    active = BooleanField(_("Active"), default=True)
    mandatory = BooleanField(_("Mandatory"), default=True)
    show_on_join = BooleanField(_("Show on Join"), default=True)
    priority = PositiveSmallIntegerField(_("Priority"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Policy")
        verbose_name_plural = _("Policies")

    if TYPE_CHECKING:
        policyversion_set: QuerySet[PolicyVersion]
        effective_version: PolicyVersion

    def __str__(self):
        return self.title

    @classmethod
    async def get_policies_to_join(cls):
        latest_versions = (
            PolicyVersion.objects
            .filter(effective_date__lte=timezone.now())
            .annotate(
                row_number=Window(
                    expression=RowNumber(),
                    partition_by=[F("policy_id")],
                    order_by=[F("effective_date").desc(), F("id").desc()],
                )
            )
            .filter(row_number=1)
            .values("id")
        )

        policies = [
            policy
            async for policy in (
                cls.objects
                .filter(show_on_join=True, active=True, policyversion__id__in=latest_versions)
                .prefetch_related(
                    Prefetch(
                        "policyversion_set",
                        queryset=PolicyVersion.objects.filter(id__in=latest_versions).order_by(
                            "-effective_date", "-id"
                        ),
                    )
                )
                .order_by("priority")
                .distinct()
            )
        ]

        effective_policies = []
        for policy in policies:
            effective_versions = policy.policyversion_set.all()  # from cache
            if effective_versions:
                policy.effective_version = effective_versions[0]
                effective_policies.append(policy)

        return effective_policies


@pghistory.track()
class PolicyVersion(TimeStampedMixin):
    policy = ForeignKey(Policy, CASCADE, verbose_name=_("Policy"))
    body = TextField(_("Body"))
    data_category = JSONField(_("Data Category"), blank=True, default=dict)
    version = CharField(_("Version"), max_length=20)
    effective_date = DateTimeField(_("Effective Date"), default=timezone.now)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Policy Version")
        verbose_name_plural = _("Policy Versions")
        constraints = [UniqueConstraint(fields=["policy", "version"], name="operation_policyversion_po_ve_uniq")]

    @classmethod
    async def get_effective_mandatory_version_ids_to_join(cls):
        version_ids = (
            cls.objects
            .filter(
                effective_date__lte=timezone.now(),
                policy__show_on_join=True,
                policy__active=True,
                policy__mandatory=True,
            )
            .annotate(
                row_number=Window(
                    expression=RowNumber(),
                    partition_by=[F("policy_id")],
                    order_by=[F("effective_date").desc(), F("id").desc()],
                )
            )
            .filter(row_number=1)
            .values_list("id", flat=True)
        )

        return [version_id async for version_id in version_ids]


@pghistory.track()
class PolicyAgreement(TimeStampedMixin):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    version = ForeignKey(PolicyVersion, CASCADE, verbose_name=_("Policy Version"))
    accepted = BooleanField(_("Accepted"), null=True, blank=True)

    class Meta(TimeStampedMixin.Meta):
        indexes = [Index(fields=["user", "accepted"])]
        verbose_name = _("Policy Agreement")
        verbose_name_plural = _("Policy Agreements")

    @classmethod
    async def agree_policies(cls, *, user_id: str, agreements: dict[str, bool | None]):
        agreement_objects = [
            cls(user_id=user_id, version_id=int(version_id), accepted=accepted)
            for version_id, accepted in agreements.items()
            if str(version_id).isdigit()
        ]
        await cls.objects.abulk_create(agreement_objects, ignore_conflicts=True)


@pghistory.track()
class Thread(TimeStampedMixin):
    title = CharField(_("Title"), max_length=255)
    description = TextField(_("Description"), blank=True, default="")
    subject_type = ForeignKey(ContentType, CASCADE, verbose_name=_("Subject Type"))
    subject_id = CharField(_("Subject ID"), max_length=36)
    subject = GenericForeignKey("subject_type", "subject_id")
    comment_count = PositiveIntegerField(_("Comment Count"), default=0)
    rating_count = PositiveIntegerField(_("Rating Count"), default=0)
    rating_sum = PositiveIntegerField(_("Rating Sum"), default=0)
    rating_avg = FloatField(_("Rating Average"), default=0)
    closed = BooleanNowField(_("Closed"), null=True, blank=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Thread")
        verbose_name_plural = _("Threads")
        constraints = [UniqueConstraint(fields=["subject_type", "subject_id"], name="opeation_thread_suty_suid_uniq")]

    if TYPE_CHECKING:
        pk: int

    def __str__(self):
        return f"{self.pk} - {self.title[:10]}"


@pghistory.track()
class Comment(TimeStampedMixin, AttachmentMixin):
    thread = ForeignKey(Thread, CASCADE, verbose_name=_("Thread"))
    parent = ForeignKey("self", CASCADE, null=True, blank=True, related_name="children", verbose_name=_("Parent"))
    comment = TextField(_("Comment"), max_length=5000)
    pinned = BooleanField(_("Pinned"), default=False)
    deleted = BooleanField(_("Deleted"), default=False)
    rating = PositiveSmallIntegerField(_("Rating"), null=True, blank=True)
    writer = ForeignKey(User, CASCADE, verbose_name=_("Writer"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Comment")
        verbose_name_plural = _("Comments")

    if TYPE_CHECKING:
        pk: int
        parent_id: int
        children: QuerySet[Comment]

    def __str__(self):
        return f"{self.pk} - {self.comment[:10]}"

    @property
    def comment_brief(self):
        content = BeautifulSoup(self.comment, "html.parser").get_text(separator=" ", strip=True)
        return content[:100] if (content and len(content) > 100) else content

    @property
    def cleaned_comment(self):
        if self.deleted:
            return "[DELETED]"
        return self.update_attachment_urls(content=self.comment)

    @classmethod
    async def upsert(cls, *, files: Sequence[File] | None, id: int | None = None, **data):
        comment, _ = await cls.objects.aupdate_or_create(id=id, defaults=data)

        await comment.update_attachments(files=files, owner_id=data.pop("writer_id"), content=comment.comment)
        return comment


setattr(Comment._meta, "triggers", thread_comment_stats(Thread._meta.db_table, Comment._meta.db_table))
