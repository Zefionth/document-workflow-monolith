"""
Настройки Django для document-workflow-monolith.

УЧЕБНЫЙ ПРОЕКТ: часть решений здесь намеренно плохие. Ищите комментарии
"АНТИПАТТЕРН" и "УЯЗВИМОСТЬ" — это точки для рефакторинга в течение семестра.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# УЯЗВИМОСТЬ: секретный ключ захардкожен и попадёт в git.
SECRET_KEY = "django-insecure-k3$9x!vq2p@d7z#h1m^c8n&f4b*w6r0t5y+u=e-a_l)j(g%s"

# УЯЗВИМОСТЬ: DEBUG включён всегда, в том числе в проде.
DEBUG = True

# УЯЗВИМОСТЬ: принимаем любой Host-заголовок.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt",
    # АНТИПАТТЕРН: все пять доменных зон (users, documents, workflow, audit, archive)
    # живут в одном приложении.
    "apps.documents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# УЯЗВИМОСТЬ: пароль к базе данных лежит прямо в коде.
# Из окружения читается только DB_HOST — чтобы тот же код работал в docker-compose.
# Переключатель USE_SQLITE оставлен только для локального запуска без Postgres.
import os

USE_SQLITE = os.getenv("USE_SQLITE") == "1"

if USE_SQLITE:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "document_workflow",
        "USER": "document_user",
        "PASSWORD": "document_password",
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": "5432",
    }}

AUTH_USER_MODEL = "documents.User"

# УЯЗВИМОСТЬ: unsalted MD5 стоит первым — все новые пароли будут хешироваться им.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.UnsaltedMD5PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# УЯЗВИМОСТЬ: валидаторы паролей отключены, можно завести пароль "1".
AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

# УЯЗВИМОСТЬ: access-токен живёт неделю и подписан тем же SECRET_KEY.
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=7),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Document Workflow API",
    "DESCRIPTION": "API внутреннего документооборота и согласования документов.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SECURITY": [{"BearerAuth": []}],
    "COMPONENT_SPLIT_REQUEST": True,
}

# АНТИПАТТЕРН: Redis сконфигурирован, но ни один прикладной сценарий его не использует.
REDIS_URL = "redis://" + os.getenv("REDIS_HOST", "localhost") + ":6379/0"
CACHES = {"default": {
    "BACKEND": "django_redis.cache.RedisCache",
    "LOCATION": REDIS_URL,
    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
}}

# АНТИПАТТЕРН: логирование по сути отключено — приложение использует print().
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}