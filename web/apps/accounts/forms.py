from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

INPUT_CLASSES = (
    "w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-ring"
)


class TailwindStyledFormMixin:
    """Aplica INPUT_CLASSES a todos los widgets de un ModelForm/Form de auth."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT_CLASSES)


class LoginForm(TailwindStyledFormMixin, AuthenticationForm):
    pass


class StyledPasswordChangeForm(TailwindStyledFormMixin, PasswordChangeForm):
    pass
