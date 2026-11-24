from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .selection import STUDENT_SELECTION_LIMIT, parse_student_ids


class StudentSearchForm(forms.Form):
    q = forms.CharField(
        label="학생 검색",
        required=True,
        min_length=1,
        max_length=100,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": (
                    "학생명·학생번호·학교·DSG ID 검색"
                ),
                "autocomplete": "off",
                "spellcheck": "false",
                "aria-label": "학생 검색어",
            }
        ),
        error_messages={
            "required": (
                "검색어를 입력해 주세요."
            ),
            "min_length": (
                "검색어를 한 글자 이상 입력해 주세요."
            ),
            "max_length": (
                "검색어는 100자 이하로 입력해 주세요."
            ),
        },
    )


class StudentSelectionField(forms.Field):
    """학생번호를 숨은 필드로 보관하고 중복 없는 목록으로 반환합니다."""

    widget = forms.HiddenInput
    default_error_messages = {
        "required": "대상 학생을 한 명 이상 선택해 주세요.",
        "max_count": "한 번에 최대 %(limit)s명까지 선택할 수 있습니다.",
    }

    def __init__(self, *args, max_count: int = STUDENT_SELECTION_LIMIT, **kwargs):
        self.max_count = max_count
        kwargs.setdefault("label", "대상 학생")
        kwargs.setdefault(
            "help_text",
            "왼쪽에서 학생을 검색한 뒤 화살표로 오른쪽 선택 목록에 추가합니다.",
        )
        super().__init__(*args, **kwargs)

    def to_python(self, value) -> list[str]:
        return parse_student_ids(value)

    def validate(self, value) -> None:
        super().validate(value)
        if len(value) > self.max_count:
            raise ValidationError(
                self.error_messages["max_count"],
                code="max_count",
                params={"limit": self.max_count},
            )

    def prepare_value(self, value) -> str:
        return ",".join(parse_student_ids(value))
