from __future__ import annotations

from django import forms


class ClassCatalogSearchForm(forms.Form):
    STATUS_CHOICES = (
        ("", "전체"),
        ("W", "대기"),
        ("P", "진행중"),
        ("E", "종료"),
        ("C", "폐강"),
    )
    METHOD_CHOICES = (
        ("", "전체"),
        ("ONLINE", "온라인"),
        ("OFFLINE", "오프라인"),
        ("ALL", "온·오프라인"),
    )

    start_date = forms.DateField(
        label="개강일 시작",
        required=False,
        widget=forms.DateInput(
            attrs={"class": "catalog-input", "type": "date"}
        ),
    )
    end_date = forms.DateField(
        label="개강일 종료",
        required=False,
        widget=forms.DateInput(
            attrs={"class": "catalog-input", "type": "date"}
        ),
    )
    status = forms.ChoiceField(
        label="수업 상태",
        required=False,
        choices=STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "catalog-select"}),
    )
    learning_method = forms.ChoiceField(
        label="수업 방식",
        required=False,
        choices=METHOD_CHOICES,
        widget=forms.Select(attrs={"class": "catalog-select"}),
    )
    q = forms.CharField(
        label="검색어",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "catalog-input",
                "placeholder": "수업명, 번호, Term, Subject, 강사, 지점",
                "autocomplete": "off",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        if start_date and end_date and start_date > end_date:
            self.add_error(
                "end_date",
                "종료일은 시작일보다 빠를 수 없습니다.",
            )
        cleaned["q"] = (cleaned.get("q") or "").strip()
        return cleaned
