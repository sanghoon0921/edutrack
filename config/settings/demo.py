"""demo 모드: 가짜(데모) 학생·성적 데이터로 기능을 고치고 확인할 때 씁니다.

실행: .\\scripts\\run.ps1   (주소 http://127.0.0.1:8000/)
"""
from .base import *  # noqa: F401,F403

DEBUG = True
STUDENT_DATA_SOURCE = "demo"
ASSESSMENT_DATA_SOURCE = "demo"
CLASS_CATALOG_DATA_SOURCE = "demo"
# 관리자가 학생 화면을 여는 것만으로 테스트 계정의 학생 연결이 바뀌지 않게 합니다.
ADMIN_AUTO_LINK_TEST_ACCOUNTS = False

# base의 DATABASES를 고치지 않고 새로 만들어, 다른 모드와 섞이지 않게 합니다.
DATABASES = {
    **DATABASES,
    "default": {**DATABASES["default"], "NAME": BASE_DIR / "data" / "demo" / "db.sqlite3"},
}
MEDIA_ROOT = BASE_DIR / "data" / "demo" / "media"
