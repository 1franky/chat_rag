"""
Django settings for config project (chat_rag).

Generado por 'django-admin startproject' y adaptado en la Fase 1 según
plan.md (sección 2.3 y 5). Toda la configuración sensible al entorno se lee
de variables de entorno (ver .env.example) para poder correr igual en local
y en Docker.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# --- Seguridad / entorno ----------------------------------------------------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-solo-para-desarrollo-local-cambiar-en-.env",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]


# --- Application definition -------------------------------------------------

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "apps.core",
    "apps.accounts",
    "apps.chat",
    "apps.ingesta",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middlewares.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.sidebar_conversations",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# --- Base de datos -----------------------------------------------------------
# SQLite en lugar de Postgres: uso 100% personal (plan.md, sección 2.1).
# DATABASE_URL con el formato `sqlite:////ruta/absoluta/db.sqlite3`
# (ver .env.example). Sin DATABASE_URL, cae a un sqlite local para dev.

_database_url = os.environ.get("DATABASE_URL", "")
if _database_url.startswith("sqlite:"):
    _db_path = Path("/" + _database_url.split("sqlite:", 1)[1].lstrip("/"))
else:
    _db_path = BASE_DIR / "db.sqlite3"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _db_path,
    }
}


# --- Auth ---------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "chat:home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Cookies de sesión (plan.md, sección 2.3). COOKIE_SECURE por defecto en 0:
# v1 se sirve por HTTP plano (sin TLS por delante, CSRF_TRUSTED_ORIGINS usa
# http:// no https://) y en la práctica los navegadores NO tratan
# http://localhost como "contexto seguro" a los efectos de la flag Secure de
# cookies (se probó y falla con 403 CSRF real) — Secure=True simplemente
# deja el cookie sin mandar. Si en algún momento se pone un reverse proxy
# con TLS delante, poner COOKIE_SECURE=1 en .env.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"


# --- Internacionalización -----------------------------------------------

LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Static / media -------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles"))

MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
