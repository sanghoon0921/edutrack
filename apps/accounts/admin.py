from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import StudentAccountLink, User


class StudentAccountLinkInline(
    admin.TabularInline,
):
    model = StudentAccountLink
    extra = 0
    fields = (
        "student_no",
        "relationship",
        "is_primary",
        "is_active",
    )


@admin.register(User)
class EduTrackUserAdmin(UserAdmin):
    list_display = (
        "username",
        "display_name",
        "role",
        "is_staff",
        "is_active",
        "last_login",
    )
    list_filter = (
        "role",
        "is_staff",
        "is_active",
    )
    search_fields = (
        "username",
        "display_name",
        "email",
    )
    inlines = (
        StudentAccountLinkInline,
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "EduTrack 권한",
            {
                "fields": (
                    "display_name",
                    "role",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "EduTrack 권한",
            {
                "fields": (
                    "display_name",
                    "role",
                )
            },
        ),
    )


@admin.register(StudentAccountLink)
class StudentAccountLinkAdmin(
    admin.ModelAdmin,
):
    list_display = (
        "user",
        "student_no",
        "relationship",
        "is_primary",
        "is_active",
        "updated_at",
    )
    list_filter = (
        "relationship",
        "is_primary",
        "is_active",
    )
    search_fields = (
        "user__username",
        "user__display_name",
        "student_no",
    )
