"""Messaging provider registry.

Add a new platform by implementing ``BaseMessagingProvider`` and registering it
in ``_PROVIDERS``. Selection order: explicit argument, VIBETEXTING_PROVIDER,
``provider`` in ~/.vibetexting.json, then iMessage.
"""

import os
from typing import Optional

from .base import BaseMessagingProvider
from .imessage import IMessageProvider
from .whatsapp import WhatsAppProvider

PROVIDER_NAMES = ("imessage", "whatsapp")
_PROVIDERS = {
    "imessage": IMessageProvider,
    "whatsapp": WhatsAppProvider,
}
DEFAULT_PROVIDER = "imessage"


def resolve_provider_name(name: Optional[str] = None) -> str:
    if name and str(name).strip():
        return str(name).strip().lower()

    env_provider = os.environ.get("VIBETEXTING_PROVIDER")
    if env_provider and env_provider.strip():
        return env_provider.strip().lower()

    try:
        from ..config import load_user_config

        configured = load_user_config().get("provider")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().lower()
    except Exception:
        pass

    return DEFAULT_PROVIDER


def get_provider(name: Optional[str] = None) -> BaseMessagingProvider:
    key = resolve_provider_name(name)
    provider_cls = _PROVIDERS.get(key)
    if provider_cls is None:
        raise ValueError(
            f"Unknown messaging provider '{key}'. Choose one of: {', '.join(PROVIDER_NAMES)}"
        )
    return provider_cls()
