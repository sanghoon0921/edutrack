from django.apps import AppConfig


class DataImportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.data_imports"
    label = "data_imports"
    verbose_name = "데이터 이전 센터"
