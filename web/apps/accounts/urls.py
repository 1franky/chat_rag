from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/borrar-datos/", views.delete_all_data, name="delete_all_data"),
]
