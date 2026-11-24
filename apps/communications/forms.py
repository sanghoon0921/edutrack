
from apps.lms.ui_forms import PublishOnCreateMixin
from pathlib import Path

from django import forms
from django.urls import reverse_lazy

from apps.accounts.models import User
from apps.learning.models import LearningGroup

from .models import Notice

# 강사가 고를 수 있는 공지 대상 그룹: 강사·학생·학부모만('관리자' 대상은 관리자만)
TEACHER_AUDIENCES = (
    Notice.Audience.TEACHER,
    Notice.Audience.STUDENT,
    Notice.Audience.PARENT,
)


ALLOWED_FILE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".jpg", ".jpeg", ".png", ".webp",
}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_IMAGE_SIZE = 10 * 1024 * 1024


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        if data:
            return [single_clean(data, initial)]
        return []


class NoticeForm(PublishOnCreateMixin, forms.ModelForm):
    audiences = forms.MultipleChoiceField(
        label="공개 대상",
        choices=Notice.Audience.choices,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "notice-audience-choice"}),
        help_text="여러 그룹을 함께 고를 수 있습니다. 네 그룹을 모두 고르면 '전체'입니다.",
        error_messages={"required": "공개 대상을 하나 이상 고르세요."},
    )
    attachments = MultipleFileField(
        label="일반 첨부파일",
        required=False,
        widget=MultipleFileInput(
            attrs={"class": "form-control", "accept": ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.jpg,.jpeg,.png,.webp"}
        ),
        help_text="여러 파일을 선택할 수 있습니다. 파일당 최대 20MB입니다.",
    )
    inline_images = MultipleFileField(
        label="본문 이미지",
        required=False,
        widget=MultipleFileInput(
            attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}
        ),
        help_text="업로드 순서대로 [[image:1]], [[image:2]] 토큰으로 본문에 삽입합니다.",
    )

    class Meta:
        model = Notice
        fields = (
            "title",
            "content",
            "category",
            "group",
            "is_pinned",
            "is_published",
        )
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "공지 제목을 입력하세요."}
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control communications-textarea",
                    "rows": 14,
                    "data-rich-paste-editor": "true",
                    "data-rich-paste-upload-url": reverse_lazy("content-editor:upload"),
                    "placeholder": "공지 내용을 입력하세요. 캡처한 이미지는 Ctrl+V로 바로 붙여넣을 수 있습니다.",
                }
            ),
            "category": forms.RadioSelect(attrs={"class": "notice-category-choice"}),
            "group": forms.Select(attrs={"class": "form-control"}),
            "is_pinned": forms.CheckboxInput(attrs={"class": "communications-checkbox"}),
            "is_published": forms.CheckboxInput(attrs={"class": "communications-checkbox"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.teacher = bool(user and user.role in (User.Role.TEACHER, User.Role.TA) and not user.is_superuser)
        # TA(11/19): 담당 반의 반 공지만 씁니다(학원 전체 공지는 관리자·강사)
        self.ta = bool(user and user.role == User.Role.TA and not user.is_superuser)
        if self.ta:
            self.fields["category"].choices = [c for c in self.fields["category"].choices if c[0] in ("", Notice.Category.CLASS)]
        if self.teacher:
            self.fields["audiences"].choices = [
                choice for choice in Notice.Audience.choices if choice[0] in TEACHER_AUDIENCES
            ]
        if self.instance.pk:
            self.fields["audiences"].initial = [
                value for value in self.instance.audiences if value in dict(self.fields["audiences"].choices)
            ]
        else:
            # 새 공지: 관리자는 전체, 강사는 학생·학부모가 기본
            self.fields["audiences"].initial = (
                [Notice.Audience.STUDENT, Notice.Audience.PARENT] if self.teacher else list(Notice.Audience.values)
            )
        # 반 공지의 반: 관리자는 모든 반, 강사는 개설했거나 담당하는 반만
        from apps.lms.access import staff_group_ids

        groups = LearningGroup.objects.order_by("title", "pk")
        if user is not None:
            groups = groups.filter(pk__in=staff_group_ids(user))
        self.fields["group"].queryset = groups
        self.fields["group"].empty_label = "반을 고르세요"
        self.fields["category"].initial = Notice.Category.CLASS if self.ta else Notice.Category.ACADEMY
        self.fields["category"].required = False  # 고르지 않으면 학원 공지(TA는 반 공지)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("category"):
            cleaned["category"] = Notice.Category.CLASS if getattr(self, "ta", False) else Notice.Category.ACADEMY
        if getattr(self, "ta", False) and cleaned.get("category") != Notice.Category.CLASS:
            self.add_error("category", "TA는 담당 반의 반 공지만 쓸 수 있습니다.")
        if cleaned.get("category") == Notice.Category.CLASS:
            if not cleaned.get("group"):
                self.add_error("group", "반 공지는 반을 골라야 합니다.")
        else:
            cleaned["group"] = None
        return cleaned

    def save(self, commit=True):
        chosen = set(self.cleaned_data.get("audiences", []))
        if self.teacher and self.instance.for_admin:
            chosen.add(Notice.Audience.ADMIN)  # 강사가 고칠 때 화면에 없는 '관리자' 대상은 그대로 둠
        self.instance.set_audiences(chosen)
        return super().save(commit=commit)

    def clean_attachments(self):
        files = self.cleaned_data.get("attachments", [])
        for uploaded in files:
            if Path(uploaded.name).suffix.lower() not in ALLOWED_FILE_EXTENSIONS:
                raise forms.ValidationError(f"허용되지 않는 파일 형식입니다: {uploaded.name}")
            if uploaded.size > MAX_FILE_SIZE:
                raise forms.ValidationError(f"첨부파일은 20MB 이하만 가능합니다: {uploaded.name}")
        return files

    def clean_inline_images(self):
        files = self.cleaned_data.get("inline_images", [])
        for uploaded in files:
            if Path(uploaded.name).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
                raise forms.ValidationError(f"이미지 파일만 업로드할 수 있습니다: {uploaded.name}")
            if uploaded.size > MAX_IMAGE_SIZE:
                raise forms.ValidationError(f"본문 이미지는 10MB 이하만 가능합니다: {uploaded.name}")
        return files
