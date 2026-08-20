# Tailwind CSS

`input.css` es la fuente; `static/css/tailwind.css` es el artefacto
compilado con el CLI standalone de Tailwind (sin Node/npm). Se versiona en
git porque no hay build step en el Dockerfile — se sirve tal cual como
archivo estático.

`input.css` vive fuera de `static/` a propósito: si estuviera adentro,
`collectstatic`/WhiteNoise lo recolectaría e intentaría post-procesar su
`@import "tailwindcss"` como si fuera una referencia relativa a un archivo,
y fallaría.

## Recompilar tras cambiar clases en los templates

```bash
# Descargar el binario (una vez; arm64 — usar linux-x64 si tu host es amd64)
curl -fsSL -o /tmp/tailwindcss \
  https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-arm64
chmod +x /tmp/tailwindcss

# Compilar (desde web/)
/tmp/tailwindcss --input tailwind/input.css --output static/css/tailwind.css --minify
```
