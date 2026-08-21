from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.ingesta.services import delete_all_documents

from .forms import LoginForm, StyledPasswordChangeForm

# Uso 100% personal: no existe vista ni URL de registro. El único usuario se
# crea vía `manage.py createsuperuser` (ver scripts/create_admin.sh).


class LoginView(DjangoLoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(DjangoLogoutView):
    next_page = "accounts:login"


@login_required
def settings_view(request: HttpRequest) -> HttpResponse:
    """`/settings/`: cambio de contraseña + borrado de todos los datos
    (plan.md, Fase 5). El tema por defecto se maneja 100% client-side
    (localStorage, ver partials/theme_toggle.html) — acá solo hay un link
    de vuelta a esa preferencia para que quede todo en un mismo lugar."""
    if request.method == "POST":
        form = StyledPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # save() rota el hash de sesión (el password cambió) — sin esto
            # la sesión actual queda invalidada y el usuario se desloguea
            # solo por cambiar su propia contraseña.
            update_session_auth_hash(request, user)
            messages.success(request, "Contraseña actualizada.")
            return redirect("accounts:settings")
        messages.error(request, "No se pudo actualizar la contraseña — revisa los errores del formulario.")
    else:
        form = StyledPasswordChangeForm(request.user)

    return render(request, "accounts/settings.html", {"form": form})


@login_required
@require_POST
def delete_all_data(request: HttpRequest) -> HttpResponse:
    """Borra TODAS las conversaciones y TODOS los documentos (chunks en
    Qdrant incluidos). Uso 100% personal — no hay noción de "otros
    usuarios" cuyos datos preservar."""
    request.user.conversations.all().delete()
    delete_all_documents()
    messages.success(request, "Se borraron todas las conversaciones y documentos.")
    return redirect("accounts:settings")
