import json
from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

register = template.Library()

_MANIFEST_PATH = Path(settings.BASE_DIR) / "static" / "dist" / ".vite" / "manifest.json"


def _manifest() -> dict:
    try:
        return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _dev_server() -> str:
    return getattr(settings, "VITE_DEV_SERVER", "").rstrip("/")


@register.simple_tag
def vite_css(entry: str):
    if _dev_server():
        return ""
    item = _manifest().get(entry, {})
    urls = [static(f"dist/{css}") for css in item.get("css", [])]
    return format_html_join(
        "\n", '<link rel="stylesheet" href="{}">', ((url,) for url in urls)
    )


@register.simple_tag
def vite_js(entry: str):
    dev = _dev_server()
    if dev:
        return format_html(
            '<script type="module" src="{}/@vite/client"></script>\n'
            '<script type="module" src="{}/{}"></script>',
            dev,
            dev,
            entry.lstrip("/"),
        )

    item = _manifest().get(entry)
    if not item:
        if settings.DEBUG:
            # Comentário HTML constante, sem entrada do usuário.
            return mark_safe(  # nosec B308
                "<!-- assets ainda não compilados: execute npm run build -->"
            )
        raise RuntimeError(f"Entrada Vite ausente no manifesto: {entry}")

    return format_html(
        '<script type="module" src="{}"></script>', static(f"dist/{item['file']}")
    )
