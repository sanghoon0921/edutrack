"""업로드 파일(/media/…) 내보내기.

개발 서버(DEBUG)와 share·office 모드(SERVE_MEDIA)에서만 내보냅니다. 학생 제출물 같은 개인 폴더는
apps/lms/middleware.py 가 이 화면보다 먼저 막습니다.
11/24 전체 점검: 수업 자료·공지 첨부 등도 로그인한 사람만 받습니다(전에는 주소만 알면 누구나).
"""
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.views.static import serve


def media_file(request, path):
    if not (settings.DEBUG or getattr(settings, "SERVE_MEDIA", False)):
        raise Http404
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    return serve(request, path, document_root=settings.MEDIA_ROOT)
