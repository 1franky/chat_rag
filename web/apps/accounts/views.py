from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView

from .forms import LoginForm

# Uso 100% personal: no existe vista ni URL de registro. El único usuario se
# crea vía `manage.py createsuperuser` (ver scripts/create_admin.sh).


class LoginView(DjangoLoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(DjangoLogoutView):
    next_page = "accounts:login"
