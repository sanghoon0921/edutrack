from django.apps import AppConfig

class LmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.lms"
    label = "lms"
    verbose_name = "LMS 반별 학습 운영"

    def ready(self):
        from . import signals  # noqa: F401
