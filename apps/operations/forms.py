from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.utils import DatabaseError

from apps.accounts.models import User
from apps.students.services import StudentService

from .models import TeacherStudentAccess


UserModel = get_user_model()
TEXT_INPUT = {"class": "operations-input", "autocomplete": "off"}
SELECT_INPUT = {"class": "operations-select"}
CHECKBOX_INPUT = {"class": "operations-checkbox"}


def _validate_student_number(student_no: str):
    cleaned = str(student_no).strip()
    if not cleaned:
        raise forms.ValidationError("학생번호를 입력해 주세요.")
    try:
        student = StudentService().get_student(cleaned)
    except DatabaseError as error:
        raise forms.ValidationError(
            "인트라넷 학생정보를 확인하지 못했습니다. DB 연결 상태를 확인해 주세요."
        ) from error
    if student is None:
        raise forms.ValidationError("인트라넷에서 해당 학생번호를 찾지 못했습니다.")
    return student


class UserFilterForm(forms.Form):
    q = forms.CharField(
        label="검색",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={**TEXT_INPUT, "placeholder": "아이디, 이름 또는 이메일"}
        ),
    )
    role = forms.ChoiceField(
        label="역할",
        required=False,
        choices=(("", "전체 역할"), *User.Role.choices),
        widget=forms.Select(attrs=SELECT_INPUT),
    )
    link = forms.ChoiceField(
        label="학생 연결",
        required=False,
        choices=(("", "전체 연결 상태"), ("linked", "연결됨"), ("unlinked", "미연결")),
        widget=forms.Select(attrs=SELECT_INPUT),
    )


class PasswordFieldsMixin:
    password1 = forms.CharField(
        label="새 비밀번호",
        required=False,
        strip=False,
        help_text="문자 종류와 관계없이 4자 이상입니다. 변경하지 않으면 비워 두세요.",
        widget=forms.PasswordInput(attrs={**TEXT_INPUT, "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="새 비밀번호 확인",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={**TEXT_INPUT, "autocomplete": "new-password"}),
    )

    def _clean_passwords(self, cleaned_data, target_user):
        password1 = cleaned_data.get("password1") or ""
        password2 = cleaned_data.get("password2") or ""
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "비밀번호가 서로 일치하지 않습니다.")
            else:
                try:
                    validate_password(password1, user=target_user)
                except DjangoValidationError as error:
                    self.add_error("password1", error)


class ManagedUserCreateForm(PasswordFieldsMixin, forms.Form):
    username = forms.CharField(
        label="로그인 아이디",
        max_length=150,
        widget=forms.TextInput(
            attrs={**TEXT_INPUT, "autocomplete": "username", "placeholder": "로그인 아이디"}
        ),
    )
    display_name = forms.CharField(
        label="이름",
        max_length=60,
        widget=forms.TextInput(attrs={**TEXT_INPUT, "placeholder": "예: 김민준"}),
    )
    email = forms.EmailField(
        label="이메일",
        required=False,
        widget=forms.EmailInput(attrs={**TEXT_INPUT, "autocomplete": "email"}),
    )
    role = forms.ChoiceField(
        label="역할",
        choices=User.Role.choices,
        widget=forms.Select(attrs=SELECT_INPUT),
    )
    student_no = forms.CharField(
        label="연결 학생번호",
        required=False,
        max_length=50,
        widget=forms.TextInput(
            attrs={**TEXT_INPUT, "inputmode": "numeric", "placeholder": "학생·학부모 계정에만 입력"}
        ),
    )
    password1 = forms.CharField(
        label="비밀번호",
        strip=False,
        help_text="문자 종류와 관계없이 4자 이상입니다.",
        widget=forms.PasswordInput(attrs={**TEXT_INPUT, "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="비밀번호 확인",
        strip=False,
        widget=forms.PasswordInput(attrs={**TEXT_INPUT, "autocomplete": "new-password"}),
    )

    def __init__(self, *args, actor: User, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        if not actor.is_superuser:
            self.fields["role"].choices = [
                choice for choice in User.Role.choices if choice[0] != User.Role.ADMIN
            ]

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if UserModel.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("이미 사용 중인 로그인 아이디입니다.")
        return username

    def clean(self):
        cleaned = super().clean()
        self._clean_passwords(cleaned, User(username=cleaned.get("username", "")))
        role = cleaned.get("role")
        if role == User.Role.ADMIN and not self.actor.is_superuser:
            self.add_error("role", "관리자 역할 계정은 최고관리자만 생성할 수 있습니다.")
        student_no = str(cleaned.get("student_no") or "").strip()
        if role in {User.Role.STUDENT, User.Role.PARENT}:
            try:
                cleaned["student_no"] = _validate_student_number(student_no).student_id
            except forms.ValidationError as error:
                self.add_error("student_no", error)
        elif student_no:
            self.add_error("student_no", "관리자·강사 계정에는 학생번호를 연결하지 않습니다.")
        return cleaned


class ManagedUserUpdateForm(PasswordFieldsMixin, forms.Form):
    password1 = forms.CharField(
        label="새 비밀번호",
        required=False,
        strip=False,
        help_text="문자 종류와 관계없이 4자 이상입니다. 변경하지 않으면 비워 두세요.",
        widget=forms.PasswordInput(attrs={**TEXT_INPUT, "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="새 비밀번호 확인",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={**TEXT_INPUT, "autocomplete": "new-password"}),
    )
    username = forms.CharField(
        label="로그인 아이디",
        max_length=150,
        widget=forms.TextInput(attrs={**TEXT_INPUT, "autocomplete": "username"}),
    )
    display_name = forms.CharField(
        label="이름",
        max_length=60,
        widget=forms.TextInput(attrs=TEXT_INPUT),
    )
    email = forms.EmailField(
        label="이메일",
        required=False,
        widget=forms.EmailInput(attrs={**TEXT_INPUT, "autocomplete": "email"}),
    )
    role = forms.ChoiceField(
        label="역할",
        choices=User.Role.choices,
        widget=forms.Select(attrs=SELECT_INPUT),
    )

    def __init__(self, *args, target_user: User, actor: User, **kwargs):
        self.target_user = target_user
        self.actor = actor
        initial = {
            "username": target_user.username,
            "display_name": target_user.display_name,
            "email": target_user.email,
            "role": target_user.role,
        }
        initial.update(kwargs.pop("initial", {}) or {})
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        if not actor.is_superuser:
            self.fields["role"].disabled = True
            self.fields["role"].help_text = "역할 변경은 최고관리자만 할 수 있습니다."

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if UserModel.objects.filter(username__iexact=username).exclude(pk=self.target_user.pk).exists():
            raise forms.ValidationError("이미 사용 중인 로그인 아이디입니다.")
        return username

    def clean(self):
        cleaned = super().clean()
        if not self.actor.is_superuser:
            cleaned["role"] = self.target_user.role
        self._clean_passwords(cleaned, self.target_user)
        if cleaned.get("role") == User.Role.STUDENT:
            active_link_count = self.target_user.student_links.filter(is_active=True).count()
            if active_link_count > 1:
                self.add_error(
                    "role",
                    "학생 역할은 활성 학생 연결을 한 개만 가질 수 있습니다. 먼저 추가 연결을 해제해 주세요.",
                )
        return cleaned


class StudentLinkForm(forms.Form):
    student_no = forms.CharField(
        label="학생번호",
        max_length=50,
        widget=forms.TextInput(
            attrs={**TEXT_INPUT, "inputmode": "numeric", "placeholder": "인트라넷 학생번호"}
        ),
    )
    is_primary = forms.BooleanField(
        label="대표 학생으로 설정",
        required=False,
        widget=forms.CheckboxInput(attrs=CHECKBOX_INPUT),
    )

    def __init__(self, *args, target_user: User, **kwargs):
        self.target_user = target_user
        super().__init__(*args, **kwargs)

    def clean_student_no(self) -> str:
        if self.target_user.role not in {User.Role.STUDENT, User.Role.PARENT}:
            raise forms.ValidationError("학생 또는 학부모 역할에만 학생번호를 연결할 수 있습니다.")
        student = _validate_student_number(self.cleaned_data["student_no"])
        if self.target_user.role == User.Role.STUDENT:
            if self.target_user.student_links.filter(is_active=True).exclude(student_no=student.student_id).exists():
                raise forms.ValidationError("학생 계정에는 한 명의 학생만 연결할 수 있습니다.")
        return student.student_id


class TeacherStudentAccessForm(forms.Form):
    student_no = forms.CharField(
        label="담당 학생번호",
        max_length=50,
        widget=forms.TextInput(
            attrs={**TEXT_INPUT, "inputmode": "numeric", "placeholder": "인트라넷 학생번호"}
        ),
    )

    def __init__(self, *args, target_user: User, **kwargs):
        self.target_user = target_user
        super().__init__(*args, **kwargs)

    def clean_student_no(self) -> str:
        if self.target_user.role != User.Role.TEACHER:
            raise forms.ValidationError("강사 계정에만 담당 학생을 배정할 수 있습니다.")
        student = _validate_student_number(self.cleaned_data["student_no"])
        if TeacherStudentAccess.objects.filter(
            teacher=self.target_user,
            student_no=student.student_id,
            is_active=True,
        ).exists():
            raise forms.ValidationError("이미 담당 학생으로 배정되어 있습니다.")
        self.student_name = student.name
        return student.student_id
