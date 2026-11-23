import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


def env_host(name: str) -> str:
    """Aceita 'https://pub-x.r2.dev/', '//pub-x.r2.dev' ou 'pub-x.r2.dev'."""
    valor = env(name).strip()
    for prefixo in ("https://", "http://", "//"):
        if valor.startswith(prefixo):
            valor = valor[len(prefixo) :]
    return valor.strip().strip("/")


SECRET_KEY = env("SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DEBUG", True)

if not DEBUG and SECRET_KEY == "dev-insecure-key-change-me":
    raise ImproperlyConfigured("Defina SECRET_KEY em produção.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
if DEBUG:
    ALLOWED_HOSTS += ["testserver", ".localhost", "127.0.0.1"]

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

SITE_URL = env(
    "SITE_URL",
    (
        f"https://{RENDER_EXTERNAL_HOSTNAME}"
        if RENDER_EXTERNAL_HOSTNAME
        else "http://localhost:8000"
    ),
).rstrip("/")

CONFIAR_NO_PROXY = env_bool("CONFIAR_NO_PROXY", not DEBUG)

ADMIN_URL = env("ADMIN_URL", "admin/")
if not ADMIN_URL.endswith("/"):
    ADMIN_URL += "/"

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE", "43200"))
SESSION_EXPIRE_AT_BROWSER_CLOSE = env_bool("SESSION_EXPIRE_AT_BROWSER_CLOSE", False)
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True

DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
        if DEBUG
        else {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
        }
    )
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.usuarios",
    "apps.reservas",
    "apps.pagamentos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.TenantMiddleware",
    "apps.core.middleware.AssinaturaMiddleware",
    "apps.core.agendador.AgendadorMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.marca",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
        conn_health_checks=True,
    )
}

if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = env("DB_SSLMODE", "require")
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = env_bool(
        "DB_DISABLE_SERVER_SIDE_CURSORS", True
    )

AUTH_USER_MODEL = "usuarios.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGE_S3_BUCKET = env("STORAGE_S3_BUCKET")
STORAGE_S3_PRIVATE_BUCKET = env("STORAGE_S3_PRIVATE_BUCKET")
STORAGE_S3_ATIVO = bool(STORAGE_S3_BUCKET)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedStaticFilesStorage"
        )
    },
}

if STORAGE_S3_ATIVO:
    AWS_ACCESS_KEY_ID = env("STORAGE_S3_ACCESS_KEY")
    AWS_SECRET_ACCESS_KEY = env("STORAGE_S3_SECRET_KEY")
    AWS_STORAGE_BUCKET_NAME = STORAGE_S3_BUCKET
    AWS_S3_ENDPOINT_URL = env("STORAGE_S3_ENDPOINT").strip().rstrip("/") or None
    AWS_S3_REGION_NAME = env("STORAGE_S3_REGION", "auto")
    AWS_S3_ADDRESSING_STYLE = env("STORAGE_S3_ADDRESSING_STYLE", "path")
    AWS_S3_CUSTOM_DOMAIN = env_host("STORAGE_S3_PUBLIC_DOMAIN") or None
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    STORAGES["default"] = {"BACKEND": "apps.core.storage_s3.ArmazenamentoPublico"}
elif env("CLOUDINARY_CLOUD_NAME"):
    import cloudinary

    CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = env("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET")
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
        "API_KEY": CLOUDINARY_API_KEY,
        "API_SECRET": CLOUDINARY_API_SECRET,
        "SECURE": True,
    }
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )
    INSTALLED_APPS.insert(
        INSTALLED_APPS.index("django.contrib.staticfiles"), "cloudinary_storage"
    )
    STORAGES["default"] = {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"
    }

WHITENOISE_MAX_AGE = 0 if DEBUG else 31536000

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

VITE_DEV_SERVER = env("VITE_DEV_SERVER")

SITE_NOME = env("SITE_NOME", "Meu Condomínio")
CONTATO_EMAIL = env(
    "CONTATO_EMAIL", "labintelligenceappoiments@gmail.com"
)

TRIAL_DIAS = int(env("TRIAL_DIAS", "14"))
TRIAL_JANELA_DIAS = int(env("TRIAL_JANELA_DIAS", "30"))
ASSINATURA_DIAS = int(env("ASSINATURA_DIAS", "30"))
CARENCIA_DIAS = int(env("CARENCIA_DIAS", "5"))
PLANO_PIX_CHAVE = env("PLANO_PIX_CHAVE")
PLANO_PIX_BENEFICIARIO = env("PLANO_PIX_BENEFICIARIO", "MEU CONDOMINIO")
PLANO_PIX_CIDADE = env("PLANO_PIX_CIDADE", "BRASIL")
PLANO_WHATSAPP = env("PLANO_WHATSAPP")
PLANO_WHATSAPP_MENSAGEM_PADRAO = (
    "Olá! Vim pelo Meu Condomínio e preciso de ajuda.\n\n"
    "Assunto:\n"
    "1) Teste grátis\n"
    "2) Pagamento e Pix\n"
    "3) Configuração do condomínio\n"
    "4) Outro\n\n"
    "Meu nome:\n"
    "Condomínio:"
)
PLANO_WHATSAPP_MENSAGEM = env(
    "PLANO_WHATSAPP_MENSAGEM", PLANO_WHATSAPP_MENSAGEM_PADRAO
)
PLANO_WHATSAPP_MENSAGEM_LANDING_PADRAO = (
    "Olá! Vim pelo site do Meu Condomínio e quero saber mais."
)
PLANO_WHATSAPP_MENSAGEM_LANDING = env(
    "PLANO_WHATSAPP_MENSAGEM_LANDING",
    PLANO_WHATSAPP_MENSAGEM_LANDING_PADRAO,
)
EMAIL_API_PROVIDER = env("EMAIL_API_PROVIDER").strip().lower()
EMAIL_API_KEY = env("EMAIL_API_KEY")
EMAIL_API_HABILITADA = bool(EMAIL_API_KEY) and EMAIL_API_PROVIDER in {
    "brevo",
    "resend",
}
EXIGIR_CONFIRMACAO_EMAIL = env_bool(
    "EXIGIR_CONFIRMACAO_EMAIL",
    not DEBUG and (EMAIL_API_HABILITADA or bool(env("EMAIL_HOST"))),
)
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY")
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY")

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_TIMEOUT = int(env("TELEGRAM_TIMEOUT", "5"))
TAREFAS_TOKEN = env("TAREFAS_TOKEN")
AGENDADOR_INTERNO = env_bool("AGENDADOR_INTERNO", not DEBUG)

EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    "Meu Condomínio <labintelligenceappoiments@gmail.com>",
)

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "landing"
LOGOUT_REDIRECT_URL = "landing"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = "DENY"

