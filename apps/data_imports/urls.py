from django.urls import path

from . import views


app_name = "data_imports"

urlpatterns = [
    path("", views.import_dashboard, name="dashboard"),
    path("users/", views.user_import, name="user-import"),
    path("assignments/", views.assignment_import, name="assignment-import"),
    path("templates/users.csv", views.user_template, name="user-template"),
    path("templates/users-example.csv", views.user_example, name="user-example"),
    path(
        "templates/assignments.csv",
        views.assignment_template,
        name="assignment-template",
    ),
    path("batches/<int:batch_id>/", views.batch_detail, name="batch-detail"),
    path(
        "batches/<int:batch_id>/results.csv",
        views.batch_results,
        name="batch-results",
    ),
]
