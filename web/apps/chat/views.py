from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def placeholder(request):
    """Placeholder de /chat/ para la Fase 1.

    El chat real (conversaciones, streaming con el Agent SDK) se implementa
    en la Fase 4. Esta vista solo confirma que el login y el layout base
    (con el toggle de tema) funcionan.
    """
    return render(request, "chat/placeholder.html")
