from django.urls import path

from . import views

app_name = "assignments"

urlpatterns = [
    path("", views.assignment_list, name="list"),
    path("new/", views.assignment_create, name="create"),
    path("<int:assignment_id>/", views.assignment_detail, name="detail"),
    path("<int:assignment_id>/edit/", views.assignment_update, name="update"),
    path("<int:assignment_id>/delete/", views.assignment_delete, name="delete"),
    path("<int:assignment_id>/attachment/", views.assignment_attachment_download, name="attachment"),
    path("my/", views.my_assignments, name="my"),
    path("my/<int:recipient_id>/", views.my_assignment_detail, name="my-detail"),
    path("my/<int:recipient_id>/attachment/", views.my_assignment_attachment_download, name="my-attachment"),
    path("my/<int:recipient_id>/submission/", views.my_submission_attachment_download, name="my-submission-attachment"),
    path("submissions/<int:submission_id>/review/", views.submission_review, name="review"),
    path("submissions/<int:submission_id>/file/", views.submission_attachment_download, name="submission-attachment"),
]
