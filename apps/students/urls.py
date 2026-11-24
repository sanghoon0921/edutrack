from django.urls import path

from . import views


app_name = "students"


from . import bulk_selector

urlpatterns = [
    path("selector/browse/", bulk_selector.selector_browse, name="selector-browse"),
    path("selector/options/", bulk_selector.selector_options, name="selector-options"),
    path("api/student-selector/", views.student_selector_search, name="selector-search"),
    path(
        "",
        views.student_list,
        name="list",
    ),
    path(
        "me/",
        views.my_student_detail,
        name="my-detail",
    ),
    path(
        (
            "<str:student_id>/"
            "courses/<str:assign_id>/attendance/"
        ),
        views.attendance_detail,
        name="attendance",
    ),
    path(
        "<str:student_id>/",
        views.student_detail,
        name="detail",
    ),
]
