"""Checks the WhatsApp provider against a stub of the local bridge.

No WhatsApp account or Node process needed:

    python3 test_whatsapp_provider.py
"""

import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8798
os.environ["VIBETEXTING_WHATSAPP_URL"] = f"http://127.0.0.1:{PORT}"
os.environ["VIBETEXTING_WHATSAPP_AUTOSTART"] = "0"

from vibetexting.providers.whatsapp import WhatsAppProvider  # noqa: E402

ALICE = "15551234567@s.whatsapp.net"
GROUP = "120363000000000000@g.us"

STATE = {"connected": True, "sent": []}

CHATS = [
    {"chat_id": ALICE, "label": "Alice", "is_group": False, "participant_count": 1, "last_ts": 1700000200},
    {"chat_id": GROUP, "label": "Beach Trip", "is_group": True, "participant_count": 4, "last_ts": 1700000100},
]

MESSAGES = {
    ALICE: [
        {"ts": 1700000000, "from_me": True, "sender": "Me", "text": "hey", "media_path": None},
        {"ts": 1700000100, "from_me": False, "sender": "Alice", "text": "yo, free tonight?", "media_path": None},
    ],
    GROUP: [
        {"ts": 1700000000, "from_me": False, "sender": "Bob", "text": "beach?", "media_path": None},
        {"ts": 1700000100, "from_me": True, "sender": "Me", "text": "I'm in", "media_path": None},
    ],
}


class StubBridge(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/health":
            return self._json(200, {"ok": True, "connected": STATE["connected"], "qr_ascii": None})

        if not STATE["connected"]:
            return self._json(503, {"error": "WhatsApp is not linked yet"})

        if parsed.path == "/chats":
            limit = int(query.get("limit", ["50"])[0])
            return self._json(200, CHATS[:limit])

        if parsed.path == "/messages":
            chat_id = query.get("chat_id", [""])[0]
            limit = int(query.get("limit", ["20"])[0])
            chat = next((c for c in CHATS if c["chat_id"] == chat_id), None)
            if chat is None:
                return self._json(404, {"error": "unknown chat"})
            messages = MESSAGES.get(chat_id, [])[-limit:]
            return self._json(
                200,
                {
                    "chat_id": chat_id,
                    "label": chat["label"],
                    "is_group": chat["is_group"],
                    "participant_count": chat["participant_count"],
                    "participants": [ALICE, "15550000001@s.whatsapp.net"] if chat["is_group"] else [],
                    "total_count": len(MESSAGES.get(chat_id, [])),
                    "last_is_from_me": bool(messages[-1]["from_me"]) if messages else False,
                    "messages": messages,
                },
            )

        if parsed.path == "/search":
            chat_id = query.get("chat_id", [""])[0]
            term = query.get("q", [""])[0].lower()
            limit = int(query.get("limit", ["5"])[0])
            hits = [m for m in MESSAGES.get(chat_id, []) if term and term in m["text"].lower()]
            return self._json(200, {"chat_id": chat_id, "messages": hits[-limit:]})

        return self._json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/send":
            return self._json(404, {"error": "not found"})
        if not STATE["connected"]:
            return self._json(503, {"error": "WhatsApp is not linked yet"})
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        STATE["sent"].append(body)
        return self._json(200, {"ok": True})


def run_checks():
    failures = []

    def check(name, condition, detail=""):
        if condition:
            print(f"PASS  {name}")
        else:
            print(f"FAIL  {name}{f' — {detail}' if detail else ''}")
            failures.append(name)

    provider = WhatsAppProvider()

    chats = provider.get_recent_chats(limit=10)
    check("get_recent_chats returns both chats", len(chats) == 2, str(chats))
    check(
        "get_recent_chats preserves jids as ids",
        {c["chat_id"] for c in chats} == {ALICE, GROUP},
        str([c["chat_id"] for c in chats]),
    )
    check("dm participant_count is 1", chats[0]["participant_count"] == 1, str(chats[0]))

    history, total, label, is_group, context, chat_id, guid, last_me = provider.load_history(
        "alice", limit=20
    )
    check("name match resolves the dm", chat_id == ALICE, str(chat_id))
    check("label comes from the bridge", label == "Alice", str(label))
    check("total_count comes from the bridge", total == 2, str(total))
    check("dm is not a group", is_group is False)
    check("last message is inbound", last_me is False, str(last_me))
    check("chat_guid matches the jid", guid == ALICE, str(guid))
    lines = history.split("\n")
    check("history has one line per message", len(lines) == 2, history)
    check(
        "history line format is [time] speaker: text",
        bool(re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] Alice: yo, free tonight\?$", lines[1])),
        lines[1],
    )
    check("our own messages are attributed to Me", lines[0].endswith("Me: hey"), lines[0])

    pinned_history, _, pinned_label, pinned_group, pinned_context, _, _, pinned_last = provider.load_history(
        "whatever", limit=20, chat_id=GROUP
    )
    check("pinned chat id skips name matching", pinned_label == "Beach Trip", pinned_label)
    check("group flag is detected", pinned_group is True)
    check(
        "group context mentions participants",
        bool(pinned_context and "participants" in pinned_context),
        str(pinned_context),
    )
    check("group last message is ours", pinned_last is True, str(pinned_last))

    empty = provider.load_history("nobody", limit=20)
    check("unknown contact returns an empty tuple", empty[:2] == ("", 0), str(empty[:2]))

    check(
        "send_message uses the pinned jid",
        provider.send_message("Alice", "hello there", chat_id=ALICE) is True,
    )
    check("bridge received the send", STATE["sent"][-1] == {"chat_id": ALICE, "text": "hello there"}, str(STATE["sent"]))

    check(
        "send_message resolves a name when no jid is pinned",
        provider.send_message("Beach Trip", "beach?") is True,
    )
    check("resolved jid belongs to the group", STATE["sent"][-1]["chat_id"] == GROUP, str(STATE["sent"][-1]))

    memories = provider.search_memories(ALICE, "tonight")
    check("search_memories returns matching lines", "yo, free tonight?" in memories, memories)

    STATE["connected"] = False
    try:
        check("unlinked bridge returns no chats", provider.get_recent_chats() == [])
        unlinked = provider.load_history("alice")
        check("unlinked bridge returns an empty tuple", unlinked[:2] == ("", 0), str(unlinked[:2]))
        check("unlinked bridge rejects sends", provider.send_message("Alice", "hi", chat_id=ALICE) is False)
    finally:
        STATE["connected"] = True

    return failures


def main():
    server = HTTPServer(("127.0.0.1", PORT), StubBridge)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        failures = run_checks()
    finally:
        server.shutdown()
        server.server_close()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed")
        return 1
    print("All WhatsApp provider checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
