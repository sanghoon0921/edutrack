"""docs/architecture.md 의 업로드 파일 설명이 실제 차단 규칙(apps/lms/middleware.py)과 맞는지 확인합니다.

차단하는 폴더를 바꾸면 이 테스트가 실패합니다. 그때는 docs/architecture.md 의 업로드 설명도 같이 고치세요.
"""
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.lms.middleware import PrivateMediaGuardMiddleware

# 직접 주소(/media/...)로 열 수 없는 폴더: 학생이 낸 파일, 반별 학습·첨삭 파일
BLOCKED = ["lms_private/", "assignments/submissions/", "learning/discussions/", "learning/discussion-comments/"]
# 개발 서버(DEBUG)와 share·office 모드에서 주소만 알면 열리는 폴더: 강사·관리자가 올린 자료
OPEN = ["assignments/materials/", "classroom/resources/", "communications/notices/", "content-editor/pasted/"]


class ArchitectureDocUploadTests(SimpleTestCase):
    def test_doc_matches_private_media_guard(self):
        guard = PrivateMediaGuardMiddleware(lambda request: HttpResponse("served"))
        factory = RequestFactory()
        for folder in BLOCKED:
            self.assertEqual(guard(factory.get(f"{settings.MEDIA_URL}{folder}x.pdf")).status_code, 404, folder)
        for folder in OPEN:
            self.assertEqual(guard(factory.get(f"{settings.MEDIA_URL}{folder}x.pdf")).content, b"served", folder)
        doc = (Path(settings.BASE_DIR) / "docs" / "architecture.md").read_text(encoding="utf-8")
        self.assertEqual([folder for folder in BLOCKED + OPEN if f"`{folder}`" not in doc], [])
