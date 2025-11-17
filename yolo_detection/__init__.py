# Inizializza Celery quando Django parte
from .celery import app as celery_app  # type: ignore[attr-defined]

__all__ = ("celery_app",)
