from django.contrib import admin

from .models import (
    Assignment,
    AssignmentRecipient,
    Submission,
)


class AssignmentRecipientInline(
    admin.TabularInline
):
    model = AssignmentRecipient
    extra = 0
    readonly_fields = (
        "student_id",
        "student_name",
        "created_at",
    )


@admin.register(Assignment)
class AssignmentAdmin(
    admin.ModelAdmin
):
    list_display = (
        "title",
        "created_by",
        "due_at",
        "is_published",
        "created_at",
    )
    list_filter = (
        "is_published",
        "due_at",
    )
    search_fields = (
        "title",
        "description",
        "created_by__username",
    )
    inlines = (
        AssignmentRecipientInline,
    )


@admin.register(Submission)
class SubmissionAdmin(
    admin.ModelAdmin
):
    list_display = (
        "recipient",
        "submitted_at",
        "feedback_at",
    )
    search_fields = (
        "recipient__student_id",
        "recipient__student_name",
        "recipient__assignment__title",
    )


@admin.register(AssignmentRecipient)
class AssignmentRecipientAdmin(
    admin.ModelAdmin
):
    list_display = (
        "assignment",
        "student_id",
        "student_name",
        "status_label",
    )
    search_fields = (
        "student_id",
        "student_name",
        "assignment__title",
    )
