from django.urls import path

from . import teacher_self_assignment, views, class_student_search

app_name = "operations"

urlpatterns = [
    path("my-students/classes/", class_student_search.class_search, name="teacher-class-search"),
    path("my-students/", teacher_self_assignment.teacher_student_assignment, name="teacher-student-assignment"),
    path("my-students/update/", teacher_self_assignment.teacher_student_assignment_update, name="teacher-student-assignment-update"),
    path("", views.operations_dashboard, name="dashboard"),
    path("users/", views.user_list, name="user-list"),
    path("users/create/", views.user_create, name="user-create"),
    path("users/<int:user_id>/", views.user_detail, name="user-detail"),
    path("users/<int:user_id>/edit/", views.user_update, name="user-update"),
    path("users/<int:user_id>/links/add/", views.link_add, name="link-add"),
    path("users/<int:user_id>/links/<int:link_id>/primary/", views.link_primary, name="link-primary"),
    path("users/<int:user_id>/links/<int:link_id>/deactivate/", views.link_deactivate, name="link-deactivate"),
    path("users/<int:user_id>/teacher-students/add/", views.teacher_access_add, name="teacher-access-add"),
    path("users/<int:user_id>/teacher-students/<int:access_id>/remove/", views.teacher_access_remove, name="teacher-access-remove"),
    path("audit/", views.audit_list, name="audit-list"),
    path("intranet-sync/", views.intranet_sync_list, name="intranet-sync"),
]
