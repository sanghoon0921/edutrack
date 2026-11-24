import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.demo")
application = get_wsgi_application()

# 운영 서버 모드(DAILY_BACKUP=True): 켜 둔 동안 하루 한 번 DB·업로드 파일 백업(14일 보관). 기본은 꺼져 있음.
from config import db_backup  # noqa: E402

db_backup.start_daily()
