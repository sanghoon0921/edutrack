from apps.assignments import views as assignment_views
from django.urls import path

from . import views, home_views
from .admin_class_detail import admin_class_detail

urlpatterns = [
    path("", views.home, name="dashboard"),
    path("home/today/", home_views.today_schedule, name="home-today"),
    path("home/insights/", home_views.home_insights, name="home-insights"),
    path("admin/students/", views.admin_students, name="admin_students"),
    path("admin/classes/", views.admin_classes, name="admin_classes"),
    path("admin/assignments/", assignment_views.assignment_list, name="admin_assignments"),
    path("admin/operations/", views.admin_operations, name="admin_operations"),
    path("teacher/classes/", views.teacher_classes, name="teacher_classes"),
    path("teacher/students/", views.teacher_students, name="teacher_students"),
    path("teacher/assignments/", assignment_views.assignment_list, name="teacher_assignments"),
    path("teacher/grades/", views.teacher_grades, name="teacher_grades"),
    path("student/classes/", views.student_classes, name="student_classes"),
    path("student/attendance/", views.student_attendance, name="student_attendance"),
    path("student/assignments/", assignment_views.my_assignments, name="student_assignments"),
    path("student/grades/", views.student_grades, name="student_grades"),
    # EDUTRACK_ADMIN_CLASS_DETAIL_V1_START
    path(
        "admin/classes/<int:class_no>/",
        admin_class_detail,
        name="admin-class-detail",
    ),
    # EDUTRACK_ADMIN_CLASS_DETAIL_V1_END
]
