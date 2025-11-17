#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yolo_detection.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Impossibile importare Django. Sei sicuro che sia installato e che PYTHONPATH sia corretto?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
