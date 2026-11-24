"""Form-only ergonomics. No model, permission, or historical visibility migration."""
from django import forms


class PublishOnCreateMixin:
    publication_field = "is_published"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        key = self.publication_field
        self.fields.pop(key, None)
        existing = bool(self.instance.pk)
        self.publication_is_private = existing and not getattr(self.instance, key)
        # Old drafts stay private unless the clearly labelled button is used.
        self._publish_requested = not existing or (self.is_bound and self.data.get("publish_now") == "1")
        if self._publish_requested:
            setattr(self.instance, key, True)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = min(int(field.widget.attrs.get("rows", 5)), 5)
            if name in {"available_from", "due_at"}:
                field.widget.attrs.update({"data-quick-datetime": name, "step": 60})
        # 공개 시작은 비워 두면 저장 즉시 공개됩니다. 화면의 '공개 시간 예약'을 켤 때만 입력합니다.

    def save(self, commit=True):
        if self._publish_requested:
            setattr(self.instance, self.publication_field, True)
        return super().save(commit=commit)
