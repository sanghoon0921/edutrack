from django.conf import settings
from django.http import HttpResponseNotFound

class PrivateMediaGuardMiddleware:
    """Block raw media URLs; all LMS private files go through permission views."""
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        base=str(settings.MEDIA_URL).rstrip('/')+'/'
        prefixes=(base+'lms_private/',base+'assignments/submissions/',base+'learning/discussions/',base+'learning/discussion-comments/')
        if request.path.startswith(prefixes):
            return HttpResponseNotFound('파일은 로그인 후 자료 화면에서 열어 주세요.')
        return self.get_response(request)
