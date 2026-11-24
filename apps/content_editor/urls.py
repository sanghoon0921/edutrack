from django.urls import path

from . import views

app_name = "content-editor"

urlpatterns = [
    path("upload/", views.upload_pasted_image, name="upload"),
    path("images/<uuid:token>/", views.pasted_image, name="image"),
]
