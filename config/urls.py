from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from . import health
from .media import media_file


urlpatterns = [
    path("lms/", include("apps.lms.urls")),
    path("health/live/", health.live, name="health-live"),
    path("health/ready/", health.ready, name="health-ready"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("students/", include("apps.students.urls")),
    path("billing/", include("apps.billing.urls")),
    path("assessments/", include("apps.assessments.urls")),
    path("assignments/", include("apps.assignments.urls")),
    path("learning/", include("apps.learning.urls")),
    path("communications/", include("apps.communications.urls")),
    path("operations/imports/", include("apps.data_imports.urls")),
    path("operations/", include("apps.operations.urls")),
    path("content-editor/", include("apps.content_editor.urls")),
    path("courses/", include("apps.classroom.urls")),
    path("reports/", include("apps.reports.urls")),
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
]


# 업로드 파일: 개발 서버(DEBUG)와 share 모드에서만 내보냅니다(config/media.py).
urlpatterns += [re_path(r"^%s(?P<path>.*)$" % settings.MEDIA_URL.lstrip("/"), media_file, name="media-file")]


handler403 = "apps.dashboard.views.permission_denied"
handler404 = "apps.dashboard.views.page_not_found"
