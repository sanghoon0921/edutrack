from django.urls import path

from . import views


app_name = "assessments"


urlpatterns = [
    path(
        (
            "students/<str:student_id>/"
            "insights/"
        ),
        views.student_learning_insight,
        name="student-insight",
    ),
    path(
        (
            "students/<str:student_id>/"
            "attempts/<str:attempt_id>/"
        ),
        views.attempt_detail,
        name="attempt-detail",
    ),
]
