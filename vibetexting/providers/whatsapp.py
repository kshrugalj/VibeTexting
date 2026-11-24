"""WhatsApp provider.

Talks to the local ``vibetexting-whatsapp`` bridge (a Node process that links
WhatsApp as a companion device). Everything stays on this machine: the bridge
listens on 127.0.0.1 and only talks to WhatsApp itself.
"""

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib import error, parse, request

from .base import BaseMessagingProvider
from ..utils import fuzzy_name_match, normalize_chat_key
from ..vision import describe_image

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8787"
BRIDGE_URL = os.environ.get("VIBETEXTING_WHATSAPP_URL", DEFAULT_BRIDGE_URL).rstrip("/")
BRIDGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vibetexting-whatsapp",
)
BRIDGE_LOG = os.path.join(os.path.expanduser("~"), ".vibetexting", "whatsapp_bridge.log")
START_TIMEOUT = float(os.environ.get("VIBETEXTING_WHATSAPP_START_TIMEOUT", "30"))
AUTOSTART = os.environ.get("VIBETEXTING_WHATSAPP_AUTOSTART", "1") not in {"0", "false", "no"}


class WhatsAppBridgeError(RuntimeError):
    """Raised when the local WhatsApp bridge is missing or unreachable."""


def _http(method: str, path: str, payload: Optional[dict] = None, timeout: float = 10) -> dict:
    url = f"{BRIDGE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise WhatsAppBridgeError(f"WhatsApp bridge returned {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise WhatsAppBridgeError(
            f"Could not reach the WhatsApp bridge at {BRIDGE_URL}: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise WhatsAppBridgeError(f"WhatsApp bridge request failed: {exc}") from exc


def _health() -> Optional[dict]:
    try:
        return _http("GET", "/health", timeout=3)
    except Exception:
        return None


def _jid_display(jid: str) -> str:
    user = str(jid or "").split("@")[0].split(":")[0]
    return f"+{user}" if user.isdigit() else (user or "Them")


def _format_lines(messages: List[dict], resolve_media: bool = True) -> List[str]:
    lines = []
    for message in messages:
        text = (message.get("text") or "").replace("\ufffc", "").replace("\n", " ").strip()
        media_path = message.get("media_path")
        if resolve_media and media_path and os.path.exists(os.path.expanduser(media_path)):
            description = describe_image(media_path)
            text = f"{text} {description}".strip() if text else description
        ts = message.get("ts") or 0
        try:
            stamp = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError, OverflowError):
            stamp = "unknown-time"
        lines.append(f"[{stamp}] {message.get('sender') or 'Them'}: {text or '[Message]'}")
    return lines


class WhatsAppProvider(BaseMessagingProvider):
    """WhatsApp implementation backed by the local Baileys bridge."""

    accepts_platform_chat_id = True

    def __init__(self):
        self._announced_qr = None
        self._announced_unlinked = False
        self._start_attempted = False
        self._last_start_failure = 0.0

    # -- bridge lifecycle ---------------------------------------------------

    def ensure_bridge(self) -> bool:
        """Start the local bridge if it is not already running."""
        if _health() is not None:
            return True
        if not AUTOSTART:
            return False
        if not os.path.isdir(BRIDGE_DIR):
            raise WhatsAppBridgeError(f"WhatsApp bridge not found at {BRIDGE_DIR}")
        if not os.path.isdir(os.path.join(BRIDGE_DIR, "node_modules")):
            raise WhatsAppBridgeError(
                "WhatsApp bridge dependencies are missing. Install them with:\n"
                f"  cd {BRIDGE_DIR} && npm install"
            )
        if shutil.which("node") is None:
            raise WhatsAppBridgeError("Node.js is required for WhatsApp support (node not found in PATH).")
        if self._last_start_failure and time.time() - self._last_start_failure < 30:
            raise WhatsAppBridgeError(
                f"WhatsApp bridge is not running yet; retrying shortly. See {BRIDGE_LOG}"
            )

        self._start_attempted = True
        os.makedirs(os.path.dirname(BRIDGE_LOG), exist_ok=True)
        with open(BRIDGE_LOG, "a", encoding="utf-8") as log:
            subprocess.Popen(
                ["node", "index.js"],
                cwd=BRIDGE_DIR,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )

        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            if _health() is not None:
                return True
            time.sleep(0.5)

        self._last_start_failure = time.time()
        raise WhatsAppBridgeError(
            f"WhatsApp bridge did not become ready within {int(START_TIMEOUT)}s. See {BRIDGE_LOG}"
        )

    def _status(self) -> Tuple[bool, dict]:
        """Ensure the bridge runs and report whether the device is linked."""
        health = _health()
        if health is None:
            try:
                self.ensure_bridge()
            except WhatsAppBridgeError as exc:
                print(f"⚠️ {exc}")
                return False, {}
            health = _health() or {}

        if health.get("connected"):
            self._announced_qr = None
            self._announced_unlinked = False
            return True, health

        qr_ascii = health.get("qr_ascii")
        if qr_ascii and qr_ascii != self._announced_qr:
            self._announced_qr = qr_ascii
            print("\n--- Link WhatsApp ---")
            print(qr_ascii)
            print("WhatsApp → Settings → Linked devices → Link a device\n")
        elif not qr_ascii and not self._announced_unlinked:
            self._announced_unlinked = True
            detail = health.get("error") or "waiting for a QR code"
            print(f"⚠️ WhatsApp is not linked yet ({detail}). See {BRIDGE_LOG}")
        return False, health

    # -- BaseMessagingProvider ---------------------------------------------

    def get_recent_chats(self, limit: int = 10) -> List[Dict]:
        connected, _ = self._status()
        if not connected:
            return []
        try:
            chats = _http("GET", f"/chats?limit={int(limit)}")
        except WhatsAppBridgeError as exc:
            print(f"⚠️ {exc}")
            return []

        return [
            {
                "chat_id": chat["chat_id"],
                "label": chat.get("label") or _jid_display(chat["chat_id"]),
                "participant_count": int(
                    chat.get("participant_count") or (2 if chat.get("is_group") else 1)
                ),
            }
            for chat in chats
        ]

    def _match_chats(self, chat_filter: str) -> List[Tuple[float, str, str, bool, int]]:
        """Returns (score, chat_id, label, is_group, last_ts) best match first."""
        connected, _ = self._status()
        if not connected:
            return []
        try:
            chats = _http("GET", "/chats?limit=200")
        except WhatsAppBridgeError as exc:
            print(f"⚠️ {exc}")
            return []

        normalized_term = normalize_chat_key(chat_filter)
        matches = []
        for chat in chats:
            label = chat.get("label") or ""
            jid = chat.get("chat_id") or ""
            best_score = 0.0
            for candidate in (label, jid, _jid_display(jid), jid.split("@")[0]):
                if not candidate:
                    continue
                best_score = max(best_score, fuzzy_name_match(chat_filter, candidate))
                if normalized_term and normalized_term in normalize_chat_key(candidate):
                    best_score = max(best_score, 90.0)
            if best_score > 35:
                matches.append(
                    (best_score, jid, label or _jid_display(jid), bool(chat.get("is_group")), chat.get("last_ts") or 0)
                )

        matches.sort(key=lambda item: (item[0], item[4]), reverse=True)
        return matches

    def _select_chat(self, chat_filter: str, auto_select: bool) -> Optional[str]:
        matches = self._match_chats(chat_filter)
        if not matches:
            return None
        if auto_select or len(matches) == 1:
            chat_id = matches[0][1]
            print(f"✅ Auto-selected '{matches[0][2]}' (confidence: {matches[0][0]:.1f}%)")
            return chat_id

        if matches[0][0] >= 95 and not (len(matches) > 1 and matches[1][0] >= 90):
            print(f"✅ Matched with '{matches[0][2]}'")
            return matches[0][1]

        # Reuse the same prompt as iMessage so both providers behave alike.
        from ..database import prompt_for_chat_suggestion

        options = [(score, chat_id, label, is_group) for score, chat_id, label, is_group, _ in matches]
        selected = prompt_for_chat_suggestion(options)
        return selected[1] if selected else None

    def load_history(
        self, chat_filter: str, limit: Optional[int] = None, **kwargs
    ) -> Tuple[str, int, Optional[str], bool, Optional[str], Optional[str], Optional[str], bool]:
        auto_select = kwargs.get("auto_select", False)
        pinned_chat_id = kwargs.get("chat_id")

        connected, _ = self._status()
        if not connected:
            return "", 0, None, False, None, None, None, False

        chat_id = str(pinned_chat_id) if pinned_chat_id else self._select_chat(chat_filter, auto_select)
        if not chat_id:
            return "", 0, None, False, None, None, None, False

        fetch_limit = int(limit) if limit else 200
        try:
            payload = _http(
                "GET",
                f"/messages?chat_id={parse.quote(chat_id)}&limit={max(1, min(fetch_limit, 500))}",
            )
        except WhatsAppBridgeError as exc:
            print(f"⚠️ {exc}")
            return "", 0, None, False, None, chat_id, chat_id, False

        messages = payload.get("messages") or []
        label = payload.get("label") or chat_filter
        is_group = bool(payload.get("is_group"))
        lines = _format_lines(messages)

        chat_context = None
        if is_group:
            participants = payload.get("participants") or []
            preview = [_jid_display(jid) for jid in participants[:6]]
            if len(participants) > 6:
                preview.append(f"+{len(participants) - 6} more")
            participant_line = ", ".join(preview) if preview else "unknown"
            chat_context = (
                f"Group chat context: this WhatsApp thread has "
                f"{payload.get('participant_count') or len(participants) or 'several'} participants. "
                f"Known participants: {participant_line}."
            )

        return (
            "\n".join(lines),
            int(payload.get("total_count") or len(messages)),
            label,
            is_group,
            chat_context,
            chat_id,
            chat_id,
            bool(payload.get("last_is_from_me")),
        )

    def send_message(self, recipient: str, text: str, **kwargs) -> bool:
        chat_id = kwargs.get("chat_id")
        target = str(chat_id) if chat_id else ""
        if not target or "@" not in target:
            resolved = self._select_chat(recipient, auto_select=True)
            if not resolved:
                print(f"⚠️ Could not resolve WhatsApp chat '{recipient}'.")
                return False
            target = resolved

        try:
            _http("POST", "/send", {"chat_id": target, "text": text}, timeout=30)
            return True
        except WhatsAppBridgeError as exc:
            print(f"⚠️ {exc}")
            return False

    def search_memories(self, chat_id, query: str, limit: int = 5) -> str:
        if not chat_id or not query:
            return ""
        try:
            payload = _http(
                "GET",
                f"/search?chat_id={parse.quote(str(chat_id))}&q={parse.quote(query)}&limit={int(limit)}",
            )
        except WhatsAppBridgeError:
            return ""
        return "\n".join(_format_lines(payload.get("messages") or [], resolve_media=False))
