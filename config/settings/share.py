"""share 모드: 운영팀이 다른 PC·사무실 밖에서 테스트하도록 외부 주소(Cloudflare 임시 주소)로 엽니다.

가짜(demo) 학생·성적 데이터만 씁니다. 실제 인트라넷·DSG에는 접속하지 않습니다.
계정·과제·대화 기록은 테스트용 사본 data/share/db.sqlite3 에 저장됩니다(처음 실행할 때 data/demo 에서 복사).
운영과 비슷하게 오류 상세는 화면에 보이지 않고, 오류·느린 화면은 data/share/server.log 에 남습니다.
실행: .\\scripts\\share.ps1
"""
from .demo import *  # noqa: F401,F403
from .served import with_log_file, with_whitenoise

DEBUG = False

# Cloudflare 임시 주소(https://….trycloudflare.com)로 들어오는 요청을 받습니다.
ALLOWED_HOSTS = [".trycloudflare.com", "127.0.0.1", "localhost"]
CSRF_TRUSTED_ORIGINS = ["https://*.trycloudflare.com"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DATABASES = {
    **DATABASES,
    "default": {**DATABASES["default"], "NAME": BASE_DIR / "data" / "share" / "db.sqlite3"},
}
MEDIA_ROOT = BASE_DIR / "data" / "share" / "media"
SERVE_MEDIA = True  # 개발 서버처럼 /media/ 업로드 파일을 내보냅니다(개인 폴더는 그대로 막힘)

MIDDLEWARE = with_whitenoise(MIDDLEWARE)  # scripts/share.ps1 이 collectstatic 을 먼저 실행
LOGGING = with_log_file(LOGGING, BASE_DIR / "data" / "share" / "server.log")

# CSS·JS 주소에는 ?v= 판이 붙어 있어 오래 저장해도 됩니다. 브라우저가 화면마다 다시 묻지 않게(11/10 속도).
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 7

# 학생 관리 쪽 넘김을 시험할 가짜 학생 수(11/11). 실제 학생 정보는 외부 링크에 올리지 않습니다.
DEMO_EXTRA_STUDENTS = 320
