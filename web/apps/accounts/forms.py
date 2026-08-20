from django.contrib.auth.forms import AuthenticationForm

INPUT_CLASSES = (
    "w-full rounded border border-slate-300 bg-transparent px-3 py-2 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-slate-400 "
    "dark:border-slate-700 dark:focus:ring-slate-600"
)


class LoginForm(AuthenticationForm):
    """AuthenticationForm con clases de Tailwind en los widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT_CLASSES)
