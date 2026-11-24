from django.urls import path

from . import views

app_name = "communications"

urlpatterns = [
    path("", views.notice_list, name="notice-list"),
    path("notices/<int:notice_id>/", views.notice_detail, name="notice-detail"),
    path(
        "notices/<int:notice_id>/files/<int:attachment_id>/",
        views.notice_attachment_download,
        name="notice-attachment",
    ),
    path(
        "notices/<int:notice_id>/images/<int:image_id>/",
        views.notice_inline_image,
        name="notice-inline-image",
    ),
    path("manage/", views.notice_manage, name="notice-manage"),
    path("manage/new/", views.notice_create, name="notice-create"),
    path("manage/<int:notice_id>/edit/", views.notice_update, name="notice-update"),
    path("manage/<int:notice_id>/delete/", views.notice_delete, name="notice-delete"),
    path("notifications/", views.notification_list, name="notification-list"),
    path("notifications/<int:notification_id>/open/", views.notification_open, name="notification-open"),
    path("notifications/read-all/", views.notification_mark_all_read, name="notification-read-all"),
]
