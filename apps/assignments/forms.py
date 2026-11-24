from __future__ import annotations

from apps.lms.ui_forms import PublishOnCreateMixin

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse_lazy

from apps.learning.models import LearningGroup
from apps.students.forms import StudentSelectionField

from .models import Assignment, Submission


DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class AssignmentFilterForm(forms.Form):
    q = forms.CharField(
        label="검색",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "과제명 검색"}
        ),
    )
    group = forms.ModelChoiceField(
        label="그룹",
        required=False,
        queryset=LearningGroup.objects.none(),
        empty_label="전체 그룹",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    status = forms.ChoiceField(
        label="상태",
        required=False,
        choices=(
            ("", "전체 상태"),
            ("open", "진행 중"),
            ("upcoming", "공개 예정"),
            ("closed", "마감"),
            ("draft", "임시저장"),
        ),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    date_from = forms.DateField(
        label="시작일",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    date_to = forms.DateField(
        label="종료일",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    def __init__(self, *args, group_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = group_queryset or LearningGroup.objects.none()


class AssignmentForm(PublishOnCreateMixin, forms.ModelForm):
    student_ids = StudentSelectionField()

    class Meta:
        model = Assignment
        fields = (
            "group",
            "title",
            "description",
            "available_from",
            "due_at",
            "points",
            "submission_type",
            "attachment",
            "is_published",
        )
        widgets = {
            "group": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 10,
                "data-rich-paste-editor": "true",
                "data-rich-paste-upload-url": reverse_lazy("content-editor:upload"),
                "placeholder": "과제 안내를 입력하세요. 캡처한 이미지는 Ctrl+V로 붙여넣을 수 있습니다.",
            }),
            "available_from": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format=DATETIME_FORMAT,
            ),
            "due_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format=DATETIME_FORMAT,
            ),
            "points": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["submission_type"].required = False
        self.fields["available_from"].input_formats = [DATETIME_FORMAT]
        self.fields["due_at"].input_formats = [DATETIME_FORMAT]
        groups = LearningGroup.objects.all()
        if user and not (user.is_superuser or user.role == "ADMIN"):
            from apps.lms.access import staff_group_ids
            groups = groups.filter(pk__in=staff_group_ids(user))
        self.fields["group"].queryset = groups
        self.fields["group"].label = "반"
        # 공개 시작은 비워 두면 저장하는 즉시 공개됩니다('공개 시간 예약'을 켤 때만 입력).

        if self.instance and self.instance.pk and not self.is_bound:
            self.fields["student_ids"].initial = list(
                self.instance.recipients.order_by("student_id").values_list("student_id", flat=True)
            )

    def clean_submission_type(self):
        return self.cleaned_data.get("submission_type") or "BOTH"

    def clean_attachment(self):
        from apps.lms.forms import validate_file
        return validate_file(self.cleaned_data.get("attachment"))

    def clean(self):
        cleaned = super().clean()
        available_from = cleaned.get("available_from")
        due_at = cleaned.get("due_at")
        if available_from and due_at and available_from >= due_at:
            self.add_error("due_at", "마감일은 공개 시작일 이후여야 합니다.")
        if not self.instance.pk and due_at and due_at <= timezone.now():
            self.add_error("due_at", "새 과제의 마감일은 현재 이후여야 합니다.")
        return cleaned


class SubmissionForm(forms.ModelForm):
    from apps.lms.forms import MultiFileField
    uploads = MultiFileField(label="추가 제출파일 (최대 5개)")
    remove_files = forms.ModelMultipleChoiceField(label="삭제할 기존 추가파일",required=False,queryset=Submission.objects.none(),widget=forms.CheckboxSelectMultiple())
    submission_version = forms.CharField(required=False,widget=forms.HiddenInput())
    class Meta:
        model = Submission
        fields = ("text_answer", "attachment")
        widgets = {"text_answer": forms.Textarea(attrs={"class":"form-control","rows":8})}
    def __init__(self,*args,assignment=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.assignment=assignment or (self.instance.recipient.assignment if self.instance.recipient_id else None)
        from apps.lms.models import SubmissionFile
        from apps.lms.documents import version_token
        from apps.lms.forms import PrivateFileInput
        self.fields["attachment"].widget=PrivateFileInput(attrs={"class":"form-control"})
        self.fields["remove_files"].queryset = self.instance.extra_files.all() if self.instance.pk else SubmissionFile.objects.none()
        self.fields["remove_files"].label_from_instance=lambda obj:obj.original_name
        if self.instance.pk:
            self.fields["submission_version"].initial=version_token(self.instance)
        if self.assignment and self.assignment.submission_type=="FILE":
            self.fields["text_answer"].widget=forms.HiddenInput()
        if self.assignment and self.assignment.submission_type=="TEXT":
            self.fields["attachment"].widget=forms.HiddenInput()
            self.fields["uploads"].widget=forms.HiddenInput()
    def clean_attachment(self):
        from apps.lms.forms import validate_file
        return validate_file(self.cleaned_data.get("attachment"))
    def clean(self):
        values=super().clean()
        text=(values.get("text_answer") or "").strip()
        file=values.get("attachment")
        extra=values.get("uploads",[])
        removed=values.get("remove_files",[])
        retained=self.instance.extra_files.exclude(pk__in=[f.pk for f in removed]).exists() if self.instance.pk else False
        mode=self.assignment.submission_type if self.assignment else "BOTH"
        if mode=="FILE" and not(file or extra or retained):
            self.add_error("attachment","파일 업로드 과제입니다. 제출파일을 선택하세요.")
        elif mode=="TEXT" and not text:
            self.add_error("text_answer","텍스트 답안을 입력하세요.")
        elif not(text or file or extra or retained):
            raise ValidationError("텍스트 답안 또는 제출파일 중 하나를 입력해 주세요.")
        if mode=="TEXT" and (self.files.get("attachment") or extra):
            raise ValidationError("텍스트 제출 유형에는 파일을 추가할 수 없습니다.")
        if mode=="FILE":values["text_answer"]=""
        return values


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("feedback",)
        widgets = {
            "feedback": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 9,
                    "placeholder": "학생에게 전달할 피드백을 입력하세요.",
                }
            ),
        }
