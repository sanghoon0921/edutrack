from __future__ import annotations

import json

from apps.lms.ui_forms import PublishOnCreateMixin

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse_lazy

from apps.dashboard.class_catalog import term_subject_options
from apps.students.forms import StudentSelectionField

from . import quiz_types
from .models import Discussion, DiscussionComment, LearningGroup, Quiz, QuizQuestion


DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class LearningGroupForm(forms.ModelForm):
    """반 만들기·수정. Term 은 인트라넷 Term 목록에서 고릅니다(11/20). 목록을 못 불러오면 글자로 입력하고,
    수정할 때 목록에 없는 예전 값(예: 26FW)은 '(기존 값)'으로 남깁니다."""

    class Meta:
        model = LearningGroup
        fields = ("title", "term", "description", "sort_order")
        labels = {"title": "반 이름"}
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "예: 26FW SAT 정규반(토)"}),
            "term": forms.TextInput(attrs={"class": "form-control", "placeholder": "예: 2026 가을 정규"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        options = term_subject_options()
        if not (options.ok and options.terms):
            self.fields["term"].help_text = "인트라넷 Term 목록을 불러오지 못해 직접 입력합니다(예: 2026 가을 정규)."
            return
        current = (self.instance.term or "").strip() if self.instance.pk else ""
        choices = [("", "Term을 고르세요")] + [(term, term) for term in options.terms]
        if current and current not in options.terms:
            choices.insert(1, (current, f"{current} (기존 값)"))
        self.fields["term"] = forms.ChoiceField(label="Term", choices=choices, required=False,
                                                widget=forms.Select(attrs={"class": "form-control"}),
                                                help_text="인트라넷에 등록된 Term 입니다.")


class LearningGroupCreateForm(LearningGroupForm):
    """반 만들기(11/20): 만들면서 학생(수업·반 통째로 또는 한 명씩)과 담당 TA·공동 강사를 함께 넣습니다."""

    student_ids = StudentSelectionField(required=False, label="반 학생",
                                        help_text="수업·반을 고르면 그 반 학생이 한꺼번에 나옵니다. 모두 추가하거나 이름으로 찾아 한 명씩 넣고 뺄 수 있습니다.")
    staff = forms.ModelMultipleChoiceField(label="담당 TA·공동 강사", required=False, queryset=None,
                                           widget=forms.SelectMultiple(attrs={"size": 6}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields["staff"].queryset = User.objects.filter(is_active=True, role__in=[User.Role.TEACHER, User.Role.TA]).order_by("role", "display_name", "username")
        self.fields["staff"].label_from_instance = lambda user: f"{user.effective_name} · {user.get_role_display()}"
        self.fields["staff"].help_text = ("TA(조교)는 이 반 학생 정보·반별 학습을 함께 보고 올리며 리포트카드를 씁니다(발송은 관리자). "
                                          "강사는 공지·과제·퀴즈·첨삭을 함께 작업합니다. Ctrl 을 누른 채 누르면 여러 명을 고릅니다.")


class RecipientMixin:
    """대상 학생 필드의 공통 설명을 위한 표시용 믹스인입니다."""


class ScheduleValidationMixin:
    def clean(self):
        cleaned = super().clean()
        available_from = cleaned.get("available_from")
        due_at = cleaned.get("due_at")
        if available_from and due_at and available_from >= due_at:
            self.add_error("due_at", "마감일은 공개 시작일 이후여야 합니다.")
        return cleaned


class DiscussionForm(PublishOnCreateMixin, RecipientMixin, ScheduleValidationMixin, forms.ModelForm):
    # RecipientMixin is not a Django Form class, so its declarative field is
    # repeated here to ensure Django's metaclass registers it.
    student_ids = StudentSelectionField()

    class Meta:
        model = Discussion
        fields = (
            "group",
            "title",
            "content",
            "attachment",
            "available_from",
            "due_at",
            "is_published",
        )
        widgets = {
            "group": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "content": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 11,
                "data-rich-paste-editor": "true",
                "data-rich-paste-upload-url": reverse_lazy("content-editor:upload"),
                "placeholder": "토론 안내를 입력하세요. 캡처한 이미지는 Ctrl+V로 붙여넣을 수 있습니다.",
            }),
            "available_from": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format=DATETIME_FORMAT,
            ),
            "due_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format=DATETIME_FORMAT,
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["available_from"].input_formats = [DATETIME_FORMAT]
        self.fields["due_at"].input_formats = [DATETIME_FORMAT]
        groups = LearningGroup.objects.all()
        if user and not (user.is_superuser or user.role == "ADMIN"):
            from apps.lms.access import staff_group_ids
            groups = groups.filter(pk__in=staff_group_ids(user))
        self.fields["group"].queryset = groups
        self.fields["group"].label = "반"
        if self.instance and self.instance.pk and not self.is_bound:
            self.fields["student_ids"].initial = list(
                self.instance.recipients.order_by("student_id").values_list("student_id", flat=True)
            )


class DiscussionCommentForm(forms.ModelForm):
    class Meta:
        model = DiscussionComment
        fields = ("content", "attachment")
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "토론 의견을 입력하세요.",
                }
            )
        }


class QuizForm(PublishOnCreateMixin, RecipientMixin, ScheduleValidationMixin, forms.ModelForm):
    # See DiscussionForm.student_ids. The field must be declared on the
    # concrete Django form class for reliable binding and validation.
    student_ids = StudentSelectionField()
    # 퀴즈 등록 화면에서 문항까지 한 번에(static/js/components/quiz-builder.js). 보내지 않으면 기존 문항을 건드리지 않습니다.
    questions_json = forms.CharField(required=False, widget=forms.HiddenInput(attrs={"data-quiz-questions": ""}))

    def question_items(self):
        """문항 편집 칸의 처음 값: 보낸 값(오류로 다시 그릴 때) → 저장된 문항 → 빈 목록."""
        if self.is_bound and (self.data.get("questions_json") or "").strip():
            try:
                items = json.loads(self.data["questions_json"])
            except ValueError:
                items = []
            return items if isinstance(items, list) else []
        if not self.instance.pk:
            return []
        return [{"id": q.pk, "type": q.question_type, "prompt": q.prompt, "points": q.points, "correct_text": q.correct_text,
                 "config": quiz_types.editor_data(q)} for q in self.instance.questions.prefetch_related("choices").order_by("order", "pk")]

    def clean_questions_json(self):
        raw = (self.cleaned_data.get("questions_json") or "").strip()
        if not raw:
            return None
        try:
            items = json.loads(raw)
        except ValueError:
            raise ValidationError("문항 정보를 읽지 못했습니다. 새로고침 후 다시 시도하세요.")
        if not isinstance(items, list) or len(items) > 100:
            raise ValidationError("문항은 최대 100개까지 등록할 수 있습니다.")
        kinds, cleaned, errors = dict(QuizQuestion.Type.choices), [], []
        for number, item in enumerate(items, start=1):
            item = item if isinstance(item, dict) else {}
            kind, prompt = item.get("type"), str(item.get("prompt") or "").strip()[:5000]
            try:
                points = int(item.get("points") or 0)
            except (TypeError, ValueError):
                points = 0
            if kind not in kinds:
                errors.append(f"{number}번 문항: 문항 유형을 고르세요.")
                continue
            if not prompt:
                errors.append(f"{number}번 문항: 문제를 입력하세요.")
                continue
            if not 1 <= points <= 1000:
                errors.append(f"{number}번 문항: 배점은 1~1000점으로 입력하세요.")
                continue
            correct_text, config, choices = "", {}, []
            if kind == quiz_types.SHORT:
                correct_text = str(item.get("correct_text") or "").strip()[:255]
                if not correct_text:
                    errors.append(f"{number}번 문항: 단답형 정답을 입력하세요.")
                    continue
            else:
                try:
                    config, choices = quiz_types.clean_config(kind, item.get("config") or {}, prompt)
                except ValidationError as exc:
                    errors.append(f"{number}번 문항: {exc.messages[0]}")
                    continue
            qid = item.get("id")
            cleaned.append({"id": qid if isinstance(qid, int) else None, "type": kind, "prompt": prompt, "points": points,
                            "correct_text": correct_text, "config": config, "choices": choices})
        if errors:
            raise ValidationError(errors)
        return cleaned

    class Meta:
        model = Quiz
        fields = (
            "group",
            "title",
            "description",
            "available_from",
            "due_at",
            "max_attempts",
            "is_published",
        )
        widgets = {
            "group": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "available_from": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format=DATETIME_FORMAT,
            ),
            "due_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format=DATETIME_FORMAT,
            ),
            "max_attempts": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 10}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["available_from"].input_formats = [DATETIME_FORMAT]
        self.fields["due_at"].input_formats = [DATETIME_FORMAT]
        groups = LearningGroup.objects.all()
        if user and not (user.is_superuser or user.role == "ADMIN"):
            from apps.lms.access import staff_group_ids
            groups = groups.filter(pk__in=staff_group_ids(user))
        self.fields["group"].queryset = groups
        self.fields["group"].label = "반"
        if self.instance and self.instance.pk and not self.is_bound:
            self.fields["student_ids"].initial = list(
                self.instance.recipients.order_by("student_id").values_list("student_id", flat=True)
            )


class QuizQuestionForm(forms.ModelForm):
    """유형 카드 + 편집기(static/js/components/quiz-editor.js). 편집기가 정답 구성을 config_json 에 담아 보냅니다."""
    config_json = forms.CharField(required=False, widget=forms.HiddenInput(attrs={"data-quiz-config": ""}))
    # 예전 화면의 "정답 앞에 *" 객관식 입력도 계속 받습니다.
    choices_text = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = QuizQuestion
        fields = ("question_type", "prompt", "points", "order", "correct_text")
        widgets = {
            "question_type": forms.RadioSelect(attrs={"class": "quiz-type-choice"}),
            "prompt": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "points": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "correct_text": forms.TextInput(attrs={"class": "form-control"}),
        }
        labels = {"prompt": "문제", "correct_text": "단답형 정답"}

    def posted_config(self):
        raw = (self.data.get("config_json") or "").strip()
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        if not data and self.data.get("question_type") == quiz_types.MCQ and (self.data.get("choices_text") or "").strip():
            rows = [row.strip() for row in self.data["choices_text"].splitlines() if row.strip()]
            data = {"choices": [{"text": row.lstrip("*").strip(), "correct": row.startswith("*")} for row in rows]}
        return data if isinstance(data, dict) else {}

    def editor(self):
        """편집기 처음 값: 보낸 값(오류로 다시 그릴 때) → 저장된 문항 → 빈 값."""
        if self.is_bound:
            kind, config = self.data.get("question_type") or quiz_types.MCQ, self.posted_config()
        elif self.instance.pk:
            kind, config = self.instance.question_type, quiz_types.editor_data(self.instance)
        else:
            kind, config = self.initial.get("question_type") or quiz_types.MCQ, {}
        return {"type": kind, "config": config, "modes": quiz_types.BLANK_MODES}

    def type_cards(self):
        icons = quiz_types.TYPE_INFO
        current = self.editor()["type"]
        return [{"value": value, "label": label, "icon": icons[value][0], "hint": icons[value][1], "checked": value == current}
                for value, label in QuizQuestion.Type.choices]

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("question_type")
        cleaned["config"], cleaned["parsed_choices"] = {}, []
        if kind == quiz_types.SHORT:
            if not (cleaned.get("correct_text") or "").strip():
                self.add_error("correct_text", "단답형 정답을 입력해 주세요.")
            return cleaned
        if not kind:
            return cleaned
        try:
            cleaned["config"], cleaned["parsed_choices"] = quiz_types.clean_config(kind, self.posted_config(), cleaned.get("prompt") or "")
        except ValidationError as exc:
            self.add_error(None, exc)
        cleaned["correct_text"] = ""
        return cleaned


def quiz_builder_data(form):
    """퀴즈 등록 화면의 문항 편집기(quiz-builder.js)에 넘기는 값: 문항 목록, 유형(아이콘·설명), 빈칸 응답 방식."""
    return {"items": form.question_items(), "modes": quiz_types.BLANK_MODES,
            "types": [{"value": value, "label": label, "icon": quiz_types.TYPE_INFO[value][0], "hint": quiz_types.TYPE_INFO[value][1]}
                      for value, label in QuizQuestion.Type.choices]}
