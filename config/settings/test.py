"""자동 테스트 전용 설정(.\\scripts\\test.ps1 이 사용).

실제 인트라넷·DSG DB에 접속하지 않도록 가짜(demo) 데이터를 씁니다.
테스트 DB는 실행할 때마다 메모리에 새로 만들어지므로 data/ 의 DB 파일은 건드리지 않습니다.
"""
from .base import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STUDENT_DATA_SOURCE = "demo"
ASSESSMENT_DATA_SOURCE = "demo"
MEDIA_ROOT = BASE_DIR / "data" / "test" / "media"
