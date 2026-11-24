from django.urls import path

from . import views


app_name = "billing"


urlpatterns = [
    path(
        "my/",
        views.my_payment_history,
        name="my-history",
    ),
]
