import json
import logging
import os
from pathlib import Path

import django_stubs_ext
import pghistory
from celery.schedules import crontab
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.translation import get_language_info
from django.utils.translation import gettext_lazy as _
from import_export.formats.base_formats import XLSX

# constants
PRESIGNED_GET_URL_EXPIRY: int = 60  # 1 minute
PRESIGNED_PUT_URL_EXPIRY: int = 60 * 5  # 5 minutes
ACTIVATION_TOKEN_EXPIRY: int = 60 * 60 * 24  # 1 day
EMAIL_CHANGE_TOKEN_EXPIRY: int = 60 * 60  # 1 hour
PASSWORD_CHANGE_TOKEN_EXPIRY: int = 60 * 60  # 1 hour
REFRESH_TOKEN_NAME: str = "refresh_token"
ACCESS_TOKEN_NAME: str = "access_token"
ACCESS_TOKEN_EXPIRE_SECONDS: int = 60 * 15  # 15 minutes
REFRESH_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24  # 1 day
SUBMISSION_GRACE_PERIOD: int = 5  # 5 seconds
OTP_VERIFICATION_EXPIRY: int = 60 * 5  # 5 minutes
DEFAULT_PAGINATION_SIZE: int = 24
CHILD_COMMENT_MAX_COUNT: int = 20
CHILD_POST_MAX_COUNT: int = 10
AVATAR_MAX_SIZE_MB = 3
ATTACHMENT_MAX_COUNT = 3
ATTACHMENT_MAX_SIZE_MB = 3
DEFAULT_REVIEW_PERIOD_DAYS = 30

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

SECRET_KEY = "django-insecure-session-key" if DEBUG else os.environ["SECRET_KEY"]

ALLOWED_HOSTS = ["localhost"] if DEBUG else json.loads(os.environ["ALLOWED_HOSTS"])

INSTALLED_APPS = [
    # unfold
    "unfold",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.filters",
    "unfold.contrib.import_export",
    # third-party
    "pgtrigger",
    "pghistory",
    "treebeard",
    "phonenumber_field",
    "django_opensearch_dsl",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "import_export",
    "django_cleanup.apps.CleanupConfig",
    "django_jsonform",
    # django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # apps
    "apps.common",
    "apps.account",
    "apps.operation",
    "apps.partner",
    "apps.competency",
    "apps.content",
    "apps.survey",
    "apps.quiz",
    "apps.exam",
    "apps.assignment",
    "apps.discussion",
    "apps.course",
    "apps.learning",
    "apps.store",
    "apps.tracking",
    "apps.assistant",
    "django_celery_results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "apps.account.api.middleware.cookie_auth_middleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "apps.tracking.middleware.HistoryMiddleware",
]

ROOT_URLCONF = "minima.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,  # app/templates
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

# WSGI_APPLICATION = "minima.wsgi.application"
ASGI_APPLICATION = "minima.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "minima"),
        "USER": os.environ.get("DB_USER", "minima"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "minima"),
        "HOST": os.environ.get("DB_HOST", "db"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

LANGUAGE_CODE = os.environ.get("LANGUAGE_CODE", "en-us")

TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")

USE_I18N = True

USE_TZ = True

DEFAULT_LANGUAGE = get_language_info(LANGUAGE_CODE)["code"] or "en"

DEFAULT_REGION = os.environ.get("DEFAULT_REGION", "US")

LANGUAGES = [("en", _("English")), ("ko", _("Korean"))]

LOCALE_PATHS = [BASE_DIR / "locale"]

STATICFILES_DIRS = [
    ("admin", os.path.join(BASE_DIR, "static/admin")),
    ("image", os.path.join(BASE_DIR, "static/image")),
    ("sample", os.path.join(BASE_DIR, "static/sample")),
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")

# cache
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}

# logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.db.backends": {"handlers": ["console"], "level": "DEBUG", "propagate": False}},
    "root": {"handlers": ["console"], "level": "INFO"},
}


# smtp
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "mailpit")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "1025"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Minima <support@example.com>")

# storage
S3_OPTIONS = {
    "access_key": os.environ.get("S3_ACCESS_KEY", "minima"),
    "secret_key": os.environ.get("S3_SECRET_KEY", "minima.dev"),
    "bucket_name": os.environ.get("S3_BUCKET_NAME", "minima"),
    "endpoint_url": os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
}
STORAGES = {
    "default": {"BACKEND": "apps.common.storage.DefaultStorage", "OPTIONS": {**S3_OPTIONS, "location": "media"}},
    "avatar": {
        "BACKEND": "apps.common.storage.AvatarStorage",
        "OPTIONS": {**S3_OPTIONS, "location": "avatar", "querystring_expire": REFRESH_TOKEN_EXPIRE_SECONDS},
    },
    "staticfiles": {
        "BACKEND": "apps.common.storage.ManifestStaticS3Storage",
        "OPTIONS": {**S3_OPTIONS, "location": "static", "querystring_auth": False},
    },
}
STORAGE_ADMIN_URL = "http://localhost:9001/"

STATIC_URL = "/static/"

# swappable models
AUTH_USER_MODEL = "account.User"

# platform
PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "Minima")
PLATFORM_ADDRESS = os.environ.get("PLATFORM_ADDRESS", "1234 Main St, San Francisco, CA 94123, USA")
PLATFORM_BASE_URL = os.environ.get("PLATFORM_BASE_URL", "http://www.example.com")
PLATFORM_PHONE_NUMBER = os.environ.get("PLATFORM_PHONE_NUMBER", "1234-5678")
PRIVACY_POLICY_URL = f"{PLATFORM_BASE_URL}/privacy"
TERMS_URL = f"{PLATFORM_BASE_URL}/terms"

# unfold
UNFOLD = {
    "SITE_DROPDOWN": [
        {"icon": "storage", "title": _("Storage"), "link": STORAGE_ADMIN_URL, "attrs": {"target": "_blank"}}
    ],
    "COMMAND": {"search_models": False, "show_history": True},
    "SITE_TITLE": PLATFORM_NAME,
    "SITE_HEADER": PLATFORM_NAME,
    "SITE_LOGO": {
        "light": staticfiles_storage.url("image/logo/logo.png"),
        "dark": staticfiles_storage.url("image/logo/logo.png"),
    },
    "SITE_FAVICONS": [
        {"rel": "icon", "type": "image/x-icon", "href": staticfiles_storage.url("image/favicon/favicon.ico")}
    ],
    "SHOW_LANGUAGES": True,
    "STYLES": [staticfiles_storage.url("admin/css/unfold.css")],
    "BORDER_RADIUS": "4px",
    "SIDEBAR": {"show_search": True, "command_search": True},
}

LOGIN_REDIRECT_URL = "/admin/"

# phonenumber field
PHONENUMBER_DEFAULT_REGION = os.environ.get("DEFAULT_REGION", "US")

# opensearch
OPENSEARCH_DSL = {"default": {"hosts": os.environ.get("OPENSEARCH_HOSTS", "opensearch:9200")}}
OPENSEARCH_DSL_AUTO_REFRESH = True
OPENSEARCH_TEXT_ANALYZER = os.environ.get("OPENSEARCH_TEXT_ANALYZER", "standard")
OPENSEARCH_DSL_SETTINGS = json.loads(os.environ.get("OPENSEARCH_DSL_SETTINGS", "{}")) or {
    "number_of_shards": 1,
    "number_of_replicas": 0,
}

# import_export
IMPORT_EXPORT_FORMATS = [XLSX]
IMPORT_EXPORT_SKIP_ADMIN_LOG = True
IMPORT_EXPORT_SKIP_ADMIN_EXPORT_UI = True
IMPORT_EXPORT_IMPORT_IGNORE_BLANK_LINES = True

# tika
TIKA_HOST = os.environ.get("TIKA_HOST", "http://tika:9998")

# celery
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "default"
CELERY_BEAT_SCHEDULE_FILENAME = "/tmp/celerybeat-schedule"


# pghistory
PGHISTORY_DEFAULT_TRACKERS = (
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(condition=pghistory.AnyChange(exclude_auto=True)),
    pghistory.DeleteEvent(),
)
# PGHISTORY_JSON_ENCODER = "django.core.serializers.json.DjangoJSONEncoder"
PGHISTORY_APPEND_ONLY = True  # make immutable
HOT_EVENTS_RETENTION_DAYS = 7  # 7 days

# password
PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 50
PASSWORD_REGEX = r'^(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>]).*$'
PASSWORD_HELP_TEXT = _(
    f'At least {PASSWORD_MIN_LENGTH} characters. One number and one special character (!@#$%^&*(),.?":{{}}|<>) must be included.'
)

# otp
OTP_TOTP_ISSUER = PLATFORM_NAME
OTP_TOTP_THROTTLE_FACTOR = 1

# tasks
CELERY_BEAT_SCHEDULE = {
    "sync-hot-events": {"task": "tracking.tasks.sync_hot_event", "schedule": 300.0},
    "cleanup-hot-events": {"task": "tracking.tasks.cleanup_hot_event", "schedule": crontab(hour=2, minute=0)},
}

# assistant
ASSISTANT_AGENT = os.environ.get("ASSISTANT_AGENT", "your-assistant-agent-here")
ASSISTANT_AGENT_API_KEY = os.environ.get("ASSISTANT_AGENT_API_KEY", "your-assistant-agent-api-key-here")

# font log

logging.getLogger("fontTools.subset").setLevel(logging.WARNING)
logging.getLogger("fontTools.ttLib.ttFont").setLevel(logging.WARNING)
logging.getLogger("fpdf.svg").propagate = False


# monkeypatch
django_stubs_ext.monkeypatch()

if DEBUG:
    import minima.settings_dev  # noqa
