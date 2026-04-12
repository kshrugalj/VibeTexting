import os
import json
import argparse
from typing import Optional
from .utils import normalize_chat_key

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vibetexting.json")
DEFAULT_INTENT_MODE = "uncertain"
DEFAULT_HISTORY_LIMIT = 20
INTENT_MODES = {"always", "uncertain", "suggest"}

def load_user_config() -> dict:
    config_candidates = [
        os.path.join(os.getcwd(), ".vibetexting.json"),
        DEFAULT_CONFIG_PATH,
    ]
    for config_path in config_candidates:
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            if isinstance(config, dict):
                config["__path__"] = config_path
                return config
        except Exception:
            continue
    return {}

def save_user_config(config: dict, config_path: str = DEFAULT_CONFIG_PATH) -> str:
    serializable_config = {
        key: value
        for key, value in config.items()
        if key != "__path__" and value is not None
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(serializable_config, f, indent=2)
        f.write("\n")
    return config_path

def merge_runtime_settings(args: argparse.Namespace, config: dict) -> argparse.Namespace:
    recipient_key = args.chat or config.get("default_recipient")
    recipient_config = {}
    recipients = config.get("recipients")
    if isinstance(recipients, dict) and recipient_key:
        recipient_config = recipients.get(recipient_key, {})
        if not recipient_config:
            normalized_recipient_key = normalize_chat_key(recipient_key)
            for key, value in recipients.items():
                if normalize_chat_key(key) == normalized_recipient_key:
                    recipient_config = value if isinstance(value, dict) else {}
                    recipient_key = key
                    break
    if not args.name and config.get("name"):
        args.name = config.get("name")
    if not getattr(args, "backend", None) and config.get("backend"):
        args.backend = config.get("backend")
    if not getattr(args, "model", None) and config.get("model"):
        args.model = config.get("model")
    if not getattr(args, "vibe", None) and config.get("vibe"):
        args.vibe = config.get("vibe")
    if not getattr(args, "chat", None):
        config_chat = recipient_config.get("chat") if isinstance(recipient_config, dict) else None
        if config_chat:
            args.chat = config_chat
        elif isinstance(recipient_key, str) and recipient_key:
            args.chat = recipient_key
    if getattr(args, "full", False):
        args.history_limit = None
    elif getattr(args, "history_limit", None) is None:
        recipient_history_limit = None
        if isinstance(recipient_config, dict):
            recipient_history_limit = recipient_config.get("history_limit")
        if recipient_history_limit is None and config.get("history_limit") is not None:
            recipient_history_limit = config.get("history_limit")
        
        if recipient_history_limit is not None:
            try:
                args.history_limit = int(recipient_history_limit)
            except Exception:
                args.history_limit = DEFAULT_HISTORY_LIMIT
        else:
            args.history_limit = DEFAULT_HISTORY_LIMIT
    if not getattr(args, "intent_mode", None) and config.get("intent_mode"):
        args.intent_mode = config.get("intent_mode")
    if not getattr(args, "intent_mode", None):
        args.intent_mode = DEFAULT_INTENT_MODE
    if isinstance(recipient_config, dict) and recipient_config.get("intent_mode"):
        args.intent_mode = recipient_config.get("intent_mode")
    return args
