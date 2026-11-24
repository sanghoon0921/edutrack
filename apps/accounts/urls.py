from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import EduTrackLoginView, first_setup, profile_update

urlpatterns = [
    path("login/", EduTrackLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", profile_update, name="profile"),
    path("first-setup/", first_setup, name="first-setup"),
]
