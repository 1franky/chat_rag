from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Usuario de chat_rag.

    Uso 100% personal: no hay vista de registro, el único usuario se crea
    con `manage.py createsuperuser` (ver scripts/create_admin.sh).
    """

    class ThemePreference(models.TextChoices):
        SYSTEM = "system", "Sistema"
        LIGHT = "light", "Claro"
        DARK = "dark", "Oscuro"

    theme_preference = models.CharField(
        max_length=10,
        choices=ThemePreference.choices,
        default=ThemePreference.SYSTEM,
    )

    def __str__(self) -> str:
        return self.username
