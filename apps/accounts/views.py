from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from apps.operations.models import AccountAuditLog
from apps.operations.services import record_account_audit

from .forms import FirstSetupForm, LoginForm, ProfileUpdateForm, StaffFirstSetupForm


class EduTrackLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("dashboard")


@login_required
def profile_update(request):
    form = ProfileUpdateForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        user = request.user
        before = {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
        }
        user.username = form.cleaned_data["username"]
        user.display_name = form.cleaned_data["display_name"]
        user.email = form.cleaned_data.get("email", "")
        password_changed = bool(form.cleaned_data.get("password1"))
        if password_changed:
            user.set_password(form.cleaned_data["password1"])
        user.save()
        if password_changed:
            update_session_auth_hash(request, user)
        record_account_audit(
            request=request,
            target_user=user,
            action=AccountAuditLog.Action.PROFILE_UPDATED,
            summary=f"{user.username} 계정이 내 정보를 수정했습니다.",
            metadata={
                "before": before,
                "password_changed": password_changed,
            },
        )
        messages.success(request, "내 정보를 저장했습니다.")
        return redirect("profile")
    return render(
        request,
        "accounts/profile_form.html",
        {
            "page_title": "내 정보 수정",
            "form": form,
        },
    )


@login_required
def first_setup(request):
    """학생 첫 로그인(11/17): 비밀번호 변경 + 이메일·DSG ID. 끝나면 홈으로."""
    from django.utils import timezone
    user = request.user
    if not user.needs_first_setup:
        return redirect("dashboard")
    if user.role != user.Role.STUDENT:
        # 직원(11/19): 비밀번호만 바꿉니다. 인트라넷 반영 목록(학생 이메일·DSG ID)에는 들어가지 않습니다.
        staff_form = StaffFirstSetupForm(request.POST or None, user=user)
        if request.method == "POST" and staff_form.is_valid():
            user.set_password(staff_form.cleaned_data["new_password1"])
            user.needs_first_setup = False
            user.save(update_fields=["password", "needs_first_setup"])
            update_session_auth_hash(request, user)
            record_account_audit(request=request, target_user=user, action=AccountAuditLog.Action.PROFILE_UPDATED,
                                 summary=f"{user.username} 첫 로그인 비밀번호 변경")
            messages.success(request, "비밀번호를 바꿨습니다. 이제 EduTrack을 쓸 수 있습니다.")
            return redirect("dashboard")
        return render(request, "accounts/first_setup.html", {"form": staff_form, "staff_mode": True})
    form = FirstSetupForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user.set_password(data["new_password1"])
        user.email = data["email"]
        user.dsg_login_id = data["dsg_login_id"]
        user.needs_first_setup = False
        user.first_setup_at = timezone.now()
        user.intranet_synced_at = None
        user.save(update_fields=["password", "email", "dsg_login_id", "needs_first_setup", "first_setup_at", "intranet_synced_at"])
        update_session_auth_hash(request, user)
        record_account_audit(request=request, target_user=user, action=AccountAuditLog.Action.PROFILE_UPDATED,
                             summary=f"{user.username} 첫 로그인 설정(비밀번호 변경, 이메일·DSG ID 입력)")
        messages.success(request, "비밀번호를 바꾸고 이메일·DSG ID를 저장했습니다. 이제 EduTrack을 쓸 수 있습니다.")
        return redirect("dashboard")
    return render(request, "accounts/first_setup.html", {"form": form})
