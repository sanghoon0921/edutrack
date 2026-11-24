from django.urls import path

from . import views

app_name = "classroom"

urlpatterns = [
    path("", views.board_list, name="board-list"),
    path("new/", views.board_create, name="board-create"),
    path("<int:board_id>/", views.board_detail, name="board-detail"),
    path("<int:board_id>/edit/", views.board_update, name="board-update"),
    path("<int:board_id>/delete/", views.board_delete, name="board-delete"),
    path("<int:board_id>/categories/new/", views.category_create, name="category-create"),
    path("<int:board_id>/categories/<int:category_id>/edit/", views.category_update, name="category-update"),
    path("<int:board_id>/categories/<int:category_id>/delete/", views.category_delete, name="category-delete"),
    path("<int:board_id>/categories/<int:category_id>/resources/new/", views.resource_create, name="resource-create"),
    path("resources/<int:resource_id>/", views.resource_detail, name="resource-detail"),
    path("resources/<int:resource_id>/edit/", views.resource_update, name="resource-update"),
    path("resources/<int:resource_id>/delete/", views.resource_delete, name="resource-delete"),
    path("resources/<int:resource_id>/preview/", views.resource_preview, name="resource-preview"),
    path("resources/<int:resource_id>/download/", views.resource_download, name="resource-download"),
]
