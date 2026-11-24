from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("new/", views.report_new, name="new"),
    path("my/", views.my_reports, name="my"),
    path("my/<int:card_id>/", views.my_card, name="my-card"),
    path("<int:batch_id>/", views.batch_detail, name="batch"),
    path("<int:batch_id>/publish/", views.batch_publish, name="publish"),
    path("<int:batch_id>/status/", views.batch_status, name="status"),
    path("<int:batch_id>/unpublish/", views.batch_unpublish, name="unpublish"),
    path("<int:batch_id>/cards/<int:card_id>/", views.card_edit, name="card"),
    path("<int:batch_id>/cards/<int:card_id>/view/", views.card_view, name="card-view"),
    path("<int:batch_id>/cards/<int:card_id>/print/", views.batch_print, name="card-print"),
    path("<int:batch_id>/print/", views.batch_print, name="print"),
    path("<int:batch_id>/refresh/", views.batch_refresh, name="refresh"),
    path("<int:batch_id>/mocks/", views.batch_mocks, name="mocks"),
    path("<int:batch_id>/blocks/add/", views.block_add, name="block-add"),
    path("<int:batch_id>/blocks/<slug:key>/delete/", views.block_delete, name="block-delete"),
    path("<int:batch_id>/sections/<slug:key>/toggle/", views.section_toggle, name="section-toggle"),
    path("<int:batch_id>/rows/add/", views.row_add, name="row-add"),
    path("<int:batch_id>/rows/<slug:label>/delete/", views.row_delete, name="row-delete"),
    path("<int:batch_id>/delete/", views.batch_delete, name="delete"),
]
