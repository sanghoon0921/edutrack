from __future__ import annotations

from pathlib import Path

from django import forms
from django.conf import settings

from apps.students.forms import StudentSelectionField
from apps.dashboard.class_catalog import term_subject_options

from .models import CourseBoard, CourseCategory, CourseResource


ALLOWED_FILE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".txt", ".csv", ".jpg", ".jpeg", ".png", ".webp", ".zip",
}


class _AlwaysPublishedFormMixin:
    """일반 작성 화면에서 공개 여부를 묻지 않고 항상 공개 상태로 저장합니다.

    모델 필드는 기존 비공개 자료의 접근 통제와 이전 데이터 호환을 위해 유지합니다.
    """

    def save(self, commit: bool = True):
        self.instance.is_published = True
        return super().save(commit=commit)


class CourseBoardForm(_AlwaysPublishedFormMixin, forms.ModelForm):
    student_ids = StudentSelectionField()

    class Meta:
        model = CourseBoard
        fields = ("title", "term", "subject", "description")
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "예: 26SM 문학분석 Gold B"}
            ),
            "term": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "예: 2026 여름특강"}
            ),
            "subject": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "예: Literature"}
            ),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.is_bound:
            self.fields["student_ids"].initial = list(
                self.instance.recipients.order_by("student_id").values_list(
                    "student_id", flat=True
                )
            )
        # Term·Subject 는 인트라넷에 등록된 값에서 고른다. 목록을 못 불러오면 글자 입력으로 둔다.
        self._choice_values = {}
        options = term_subject_options()
        if options.ok:
            self._use_select("term", options.terms)
            self._use_select("subject", options.subjects)
        else:
            for name in ("term", "subject"):
                self.fields[name].help_text = "인트라넷 목록을 불러오지 못해 직접 입력합니다."

    def _use_select(self, name, values):
        current = (getattr(self.instance, name, "") or "").strip() if self.instance and self.instance.pk else ""
        choices = [("", "선택 안 함")]
        if current and current not in values:
            choices.append((current, f"{current} (기존 값)"))
        choices.extend((value, value) for value in values)
        self.fields[name].widget = forms.Select(choices=choices, attrs={"class": "form-control"})
        self._choice_values[name] = {value for value, _label in choices}

    def _clean_choice(self, name):
        value = (self.cleaned_data.get(name) or "").strip()
        allowed = self._choice_values.get(name)
        if allowed is not None and value not in allowed:
            raise forms.ValidationError("목록에서 고르세요.")
        return value

    def clean_term(self):
        return self._clean_choice("term")

    def clean_subject(self):
        return self._clean_choice("subject")


class CourseCategoryForm(_AlwaysPublishedFormMixin, forms.ModelForm):
    class Meta:
        model = CourseCategory
        fields = ("title", "description")
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "예: TEXTBOOK"}
            ),
            "description": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "예: 교재와 필수 읽기 자료",
                }
            ),
        }


class CourseResourceForm(_AlwaysPublishedFormMixin, forms.ModelForm):
    class Meta:
        model = CourseResource
        fields = (
            "title",
            "resource_type",
            "description",
            "file",
            "external_url",
        )
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "예: 1. Animal Farm (GOLD W1)",
                }
            ),
            "resource_type": forms.Select(
                attrs={
                    "class": "form-control",
                    "data-resource-type": "true",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "학생에게 함께 보여줄 자료 설명을 입력합니다.",
                }
            ),
            "file": forms.ClearableFileInput(
                attrs={
                    "class": "form-control course-file-input",
                    "data-resource-file": "true",
                    "accept": ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.jpg,.jpeg,.png,.webp,.zip,.mp3,.wav,.m4a,.ogg,.flac",
                }
            ),
            "external_url": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://...",
                    "data-resource-url": "true",
                }
            ),
        }

    def __init__(self, *args, initial_type: str | None = None, **kwargs):
        initial = dict(kwargs.pop("initial", {}) or {})
        if initial_type in CourseResource.Type.values:
            initial.setdefault("resource_type", initial_type)
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

        self.fields["resource_type"].label = "등록 방식"
        self.fields["file"].label = "PDF 또는 파일 선택"
        self.fields["file"].help_text = (
            "PDF 유형은 실제 PDF 파일인지 검사합니다. 파일을 선택한 뒤 저장하세요."
        )
        self.fields["external_url"].help_text = (
            "외부 링크 유형을 선택한 경우에만 입력합니다."
        )

        selected_type = CourseResource.Type.PDF
        if self.is_bound:
            selected_type = str(
                self.data.get(self.add_prefix("resource_type"))
                or CourseResource.Type.PDF
            ).strip().upper()
        elif self.instance and self.instance.pk:
            selected_type = self.instance.resource_type
        else:
            selected_type = str(
                self.initial.get("resource_type") or CourseResource.Type.PDF
            ).strip().upper()

        if selected_type == CourseResource.Type.PDF:
            self.fields["file"].widget.attrs["accept"] = ".pdf,application/pdf"
            self.fields["file"].label = "PDF 파일 선택"
        elif selected_type == CourseResource.Type.FILE:
            self.fields["file"].label = "일반 파일 선택"

    def clean(self):
        cleaned = super().clean()
        resource_type = cleaned.get("resource_type")
        uploaded = cleaned.get("file")
        external_url = (cleaned.get("external_url") or "").strip()
        existing_file = self.instance.file if self.instance and self.instance.pk else None
        effective_file = uploaded or existing_file

        max_mb = max(1, int(getattr(settings, "COURSE_RESOURCE_MAX_MB", 25)))
        if uploaded and uploaded.size > max_mb * 1024 * 1024:
            self.add_error("file", f"파일은 {max_mb}MB 이하만 업로드할 수 있습니다.")

        if resource_type == CourseResource.Type.LINK:
            if not external_url:
                self.add_error("external_url", "외부 링크 주소를 입력해 주세요.")
            cleaned["file"] = None
        else:
            if not effective_file:
                self.add_error("file", "업로드할 파일을 선택해 주세요.")
            if uploaded:
                suffix = Path(uploaded.name).suffix.lower()
                if suffix not in ALLOWED_FILE_EXTENSIONS:
                    self.add_error("file", "허용되지 않는 파일 형식입니다.")
                if resource_type == CourseResource.Type.PDF:
                    position = uploaded.tell() if hasattr(uploaded, "tell") else 0
                    signature = uploaded.read(5)
                    if hasattr(uploaded, "seek"):
                        uploaded.seek(position)
                    if suffix != ".pdf" or signature != b"%PDF-":
                        self.add_error("file", "실제 PDF 파일만 등록할 수 있습니다.")
            elif resource_type == CourseResource.Type.PDF and existing_file:
                if Path(existing_file.name).suffix.lower() != ".pdf":
                    self.add_error("file", "PDF 유형에는 PDF 파일이 필요합니다.")
            cleaned["external_url"] = ""
        return cleaned
