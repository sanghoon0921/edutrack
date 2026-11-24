from django.contrib import admin

from .models import CourseBoard, CourseBoardRecipient, CourseCategory, CourseResource


class CourseBoardRecipientInline(admin.TabularInline):
    model = CourseBoardRecipient
    extra = 0


@admin.register(CourseBoard)
class CourseBoardAdmin(admin.ModelAdmin):
    list_display = ("title", "term", "subject", "created_by", "is_published", "updated_at")
    list_filter = ("is_published", "created_at")
    search_fields = ("title", "term", "subject", "created_by__username")
    inlines = (CourseBoardRecipientInline,)


@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "board", "sort_order", "is_published")


@admin.register(CourseResource)
class CourseResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "resource_type", "is_published", "updated_at")
    list_filter = ("resource_type", "is_published")
