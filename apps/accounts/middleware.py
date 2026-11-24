"""학생 첫 로그인 설정(11/17)을 마칠 때까지 다른 화면 대신 설정 화면으로 보냅니다."""
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

ALLOWED_PREFIXES = ("/static/", "/media/", "/favicon")


class FirstSetupMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and getattr(user, "needs_first_setup", False):
            allowed = {reverse("first-setup"), reverse("logout")}
            if request.path not in allowed and not request.path.startswith(ALLOWED_PREFIXES):
                wants_json = "application/json" in request.headers.get("Accept", "") or request.headers.get("X-Requested-With")
                if wants_json or request.method != "GET":
                    return JsonResponse({"error": "첫 로그인 설정(비밀번호·이메일)을 먼저 마쳐 주세요."}, status=403)
                return redirect("first-setup")
        return self.get_response(request)
