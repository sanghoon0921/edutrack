from django.apps import AppConfig


class ClassroomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.classroom"
    label = "classroom"
    verbose_name = "과목 자료"

    def ready(self) -> None:
        from . import signals  # noqa: F401
