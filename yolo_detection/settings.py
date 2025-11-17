from pathlib import Path
import os

# Percorsi base
BASE_DIR = Path(__file__).resolve().parent.parent

# Sicurezza / Debug
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

# App installate
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # App progetto
    "detection",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "yolo_detection.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # cartella templates/ globale
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "yolo_detection.wsgi.application"
ASGI_APPLICATION = "yolo_detection.asgi.application"

# Database (SQLite per sviluppo)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Localizzazione
LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- Celery / Redis ----
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 60 * 4  # 4 ore

# ---- Config YOLO ----
YOLO_MODEL_PATH = BASE_DIR / "models" / "yolov12_finetuned.pt"
YOLO_CONFIDENCE_THRESHOLD = float(os.environ.get("YOLO_CONF", 0.5))
YOLO_IOU_THRESHOLD = float(os.environ.get("YOLO_IOU", 0.45))

# Se vuoi forzare device: YOLO_DEVICE=cpu oppure cuda
YOLO_DEVICE = os.environ.get(
    "YOLO_DEVICE",
    "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
)

# Auth redirect
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "video_list"
LOGOUT_REDIRECT_URL = "login"

# ---- Video di esempio termici ferroviari ----
SAMPLE_VIDEOS = {
    "sample1": {
        "path": "videos/samples/termico_sample_1.mp4",
        "title": "Video termico ferroviario - Esempio 1",
    },
    "sample2": {
        "path": "videos/samples/termico_sample_2.mp4",
        "title": "Video termico ferroviario - Esempio 2",
    },
}
