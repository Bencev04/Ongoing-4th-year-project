"""Shared Jinja2 template configuration.

Provides a single factory so that every route module renders
with the same set of global variables (e.g. ``google_maps_key``).
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from common.config import get_settings

_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"


def get_templates() -> Jinja2Templates:
    """Return a configured ``Jinja2Templates`` instance.

    The returned instance has all required global variables
    (e.g. ``google_maps_key``) already injected into its
    Jinja2 environment.

    Returns:
        A ready-to-use ``Jinja2Templates`` pointing at ``app/templates/``.
    """
    tpl = Jinja2Templates(directory=_TEMPLATES_DIR)
    tpl.env.globals["google_maps_key"] = get_settings().google_maps_browser_key
    tpl.env.globals["google_maps_map_id"] = get_settings().google_maps_map_id
    return tpl
