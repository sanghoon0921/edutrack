from django import forms

from .models import ImportBatch


UPLOAD_ATTRS = {
    "class": "import-file-input",
    "accept": ".csv,text/csv",
}
SELECT_ATTRS = {"class": "operations-select"}
CHECKBOX_ATTRS = {"class": "operations-checkbox"}


class BaseImportUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV 파일",
        widget=forms.ClearableFileInput(attrs=UPLOAD_ATTRS),
        help_text="UTF-8 또는 CP949 CSV, 최대 2MB·5,000행",
    )
    mode = forms.ChoiceField(
        label="처리 방식",
        choices=ImportBatch.Mode.choices,
        initial=ImportBatch.Mode.CREATE_ONLY,
        widget=forms.Select(attrs=SELECT_ATTRS),
    )
    confirm_apply = forms.BooleanField(
        label="검증 결과를 확인했으며 실제 DB에 반영합니다.",
        required=False,
        widget=forms.CheckboxInput(attrs=CHECKBOX_ATTRS),
    )

    def clean_csv_file(self):
        uploaded = self.cleaned_data["csv_file"]
        filename = (uploaded.name or "").lower()
        if not filename.endswith(".csv"):
            raise forms.ValidationError("CSV 파일만 업로드할 수 있습니다.")
        if uploaded.size > 2 * 1024 * 1024:
            raise forms.ValidationError("CSV 파일은 2MB 이하만 업로드할 수 있습니다.")
        return uploaded

    def require_apply_confirmation(self) -> None:
        if not self.cleaned_data.get("confirm_apply"):
            self.add_error("confirm_apply", "실제 반영 전 확인란을 선택해 주세요.")


class UserImportUploadForm(BaseImportUploadForm):
    pass


class AssignmentImportUploadForm(BaseImportUploadForm):
    pass
