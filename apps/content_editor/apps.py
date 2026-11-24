from django.apps import AppConfig


class ContentEditorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.content_editor"
    label = "content_editor"
    verbose_name = "본문 이미지 편집"

    def ready(self) -> None:
        from . import signals  # noqa: F401
