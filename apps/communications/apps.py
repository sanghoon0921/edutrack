from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.communications"
    label = "communications"
    verbose_name = "공지사항·알림"

    def ready(self) -> None:
        # 과제·공지 이벤트를 사이트 내 알림으로 연결합니다.
        from . import signals  # noqa: F401
