from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import User


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="아이디",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "아이디를 입력하세요",
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="비밀번호",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "비밀번호를 입력하세요",
                "autocomplete": "current-password",
            }
        ),
    )

    lock_message = ""

    def clean(self):
        """5번 틀리면 15분 잠금(11/24, login_limit). 잠긴 동안에는 맞는 비밀번호여도 확인하지 않습니다."""
        from . import login_limit

        username = self.cleaned_data.get("username") or ""
        ip = login_limit.client_ip(self.request)
        if login_limit.is_locked(username, ip):
            self.lock_message = login_limit.LOCK_MESSAGE
            raise DjangoValidationError(login_limit.LOCK_MESSAGE, code="locked")
        try:
            cleaned = super().clean()
        except DjangoValidationError:
            login_limit.record_failure(username, ip)
            if login_limit.is_locked(username, ip):
                self.lock_message = login_limit.LOCK_MESSAGE
            raise
        login_limit.record_success(username, ip)
        return cleaned


class ProfileUpdateForm(forms.Form):
    username = forms.CharField(
        label="로그인 아이디",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "username"}),
    )
    display_name = forms.CharField(
        label="이름",
        max_length=60,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        label="이메일",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
    )
    password1 = forms.CharField(
        label="새 비밀번호",
        required=False,
        strip=False,
        help_text="변경할 때만 입력합니다. 문자 종류와 관계없이 4자 이상입니다.",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="새 비밀번호 확인",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )

    def __init__(self, *args, user: User, **kwargs):
        self.user = user

        # ``ProfileUpdateForm(request.POST or None, ...)``처럼 GET 요청에서
        # data=None이 첫 번째 위치 인수로 전달돼도 기존 계정값을 표시해야 합니다.
        # 비밀번호 필드는 initial에 넣지 않으므로 항상 빈칸으로 렌더링됩니다.
        bound_data = args[0] if args else kwargs.get("data")
        if bound_data is None:
            initial = dict(kwargs.get("initial") or {})
            initial.setdefault("username", user.username)
            initial.setdefault(
                "display_name",
                user.display_name or user.effective_name,
            )
            initial.setdefault("email", user.email)
            kwargs["initial"] = initial

        super().__init__(*args, **kwargs)

        # 브라우저 자동완성이나 재렌더링으로 비밀번호가 채워지지 않게 명시합니다.
        self.fields["password1"].initial = ""
        self.fields["password2"].initial = ""

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("이미 사용 중인 로그인 아이디입니다.")
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1") or ""
        password2 = cleaned.get("password2") or ""
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "비밀번호가 서로 일치하지 않습니다.")
            else:
                try:
                    validate_password(password1, user=self.user)
                except DjangoValidationError as error:
                    self.add_error("password1", error)
        return cleaned


class FirstSetupForm(forms.Form):
    """학생 첫 로그인(11/17): 새 비밀번호 + 이메일(필수) + DSG ID(없으면 '없음' 표시)."""
    new_password1 = forms.CharField(label="새 비밀번호", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    new_password2 = forms.CharField(label="새 비밀번호 확인", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    email = forms.EmailField(label="이메일", help_text="학원 안내와 비밀번호 찾기에 씁니다.", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    dsg_login_id = forms.CharField(label="DSG ID", max_length=80, required=False,
                                   help_text="Digital SAT Global(DSG) 로그인 아이디. 모의고사 점수를 연결하는 데 씁니다.")
    no_dsg = forms.BooleanField(label="DSG 계정이 없습니다", required=False)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user is not None and not self.is_bound:
            self.initial.setdefault("email", user.email)
            self.initial.setdefault("dsg_login_id", user.dsg_login_id)

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("new_password1"), data.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "두 비밀번호가 다릅니다.")
        elif p1:
            from django.contrib.auth import password_validation
            try:
                password_validation.validate_password(p1, self.user)
            except forms.ValidationError as error:
                self.add_error("new_password1", error)
            if self.user is not None and self.user.check_password(p1):
                self.add_error("new_password1", "관리자가 정해 준 비밀번호와 다른 비밀번호를 쓰세요.")
        dsg = (data.get("dsg_login_id") or "").strip()
        if not dsg and not data.get("no_dsg"):
            self.add_error("dsg_login_id", "DSG ID를 적거나 'DSG 계정이 없습니다'에 표시하세요.")
        data["dsg_login_id"] = "" if data.get("no_dsg") else dsg
        return data


class StaffFirstSetupForm(forms.Form):
    """직원(관리자·강사·TA) 첫 로그인(11/19): 비밀번호만 바꿉니다. 8자 이상, 영문과 숫자를 모두 넣고, 받은 비밀번호와 달라야 합니다."""
    new_password1 = forms.CharField(label="새 비밀번호", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    new_password2 = forms.CharField(label="새 비밀번호 확인", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("new_password1") or "", data.get("new_password2") or ""
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "두 비밀번호가 다릅니다.")
            return data
        if p1:
            import re
            if len(p1) < 8 or not re.search(r"[A-Za-z]", p1) or not re.search(r"[0-9]", p1):
                self.add_error("new_password1", "8자 이상으로, 영문과 숫자를 모두 넣어 주세요.")
            elif self.user is not None and self.user.check_password(p1):
                self.add_error("new_password1", "받은 비밀번호와 다른 비밀번호를 쓰세요.")
        return data
