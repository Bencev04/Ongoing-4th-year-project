"""Adapter factory and registry.

Provides ``get_adapter()`` to instantiate the correct channel adapter
based on a string key and config dict. Config is validated via Pydantic
models at construction time.
"""

import logging

from pydantic import ValidationError

from .base import MessageAdapter
from .email_smtp import EmailSmtpAdapter, SmtpConfig
from .whatsapp_link import WhatsAppLinkAdapter
from .whatsapp_twilio import TwilioConfig, WhatsAppTwilioAdapter

logger = logging.getLogger(__name__)

ADAPTER_REGISTRY: dict[str, type[MessageAdapter]] = {
    "whatsapp_link": WhatsAppLinkAdapter,
    "whatsapp_twilio": WhatsAppTwilioAdapter,
    "email_smtp": EmailSmtpAdapter,
}

# Maps adapter key → its Pydantic config model (None = no config needed)
_CONFIG_MODELS: dict[str, type | None] = {
    "whatsapp_link": None,
    "whatsapp_twilio": TwilioConfig,
    "email_smtp": SmtpConfig,
}


def get_adapter(adapter_key: str, config: dict | None = None) -> MessageAdapter:
    """Create and return an adapter instance.

    Args:
        adapter_key: One of ``"whatsapp_link"``, ``"whatsapp_twilio"``,
                     ``"email_smtp"``.
        config: Provider credentials / settings dict. Validated against
                the adapter's Pydantic config model.

    Returns:
        An initialised ``MessageAdapter`` subclass.

    Raises:
        KeyError: If ``adapter_key`` is not in the registry.
        ValueError: If the config fails validation.
    """
    adapter_cls = ADAPTER_REGISTRY.get(adapter_key)
    if adapter_cls is None:
        raise KeyError(
            f"Unknown adapter '{adapter_key}'. Available: {', '.join(ADAPTER_REGISTRY)}"
        )

    config_model = _CONFIG_MODELS.get(adapter_key)
    if config_model is not None:
        try:
            validated = config_model(**(config or {}))
        except ValidationError as exc:
            raise ValueError(
                f"Invalid config for adapter '{adapter_key}': {exc}"
            ) from exc
        return adapter_cls(validated)

    return adapter_cls(config or {})
