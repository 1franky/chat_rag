def sidebar_conversations(request):
    """Conversaciones del usuario agrupadas por fecha, para el sidebar de
    base.html. Import local para no acoplar core a chat en el arranque."""
    if not request.user.is_authenticated:
        return {}

    from apps.chat.views import grouped_conversations

    return {"sidebar_conversations": grouped_conversations(request.user)}
