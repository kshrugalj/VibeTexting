"""
feedback.py — Style Correction Feedback System
================================================
Randomly prompts the user to rate generated replies and collects written
style corrections.  Feedback is persisted to disk and injected into future
prompts so the LLM learns from corrections over time.
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime
from typing import Optional

FEEDBACK_PATH = os.path.expanduser("~/.vibetexting_feedback.json")

# Probability of asking for feedback after any given reply (1 in 4 chance).
_ASK_PROBABILITY = 0.25
# Max number of feedback notes to inject into a prompt (keeps tokens low).
_MAX_INJECT = 5

# ANSI colours (duplicated here to avoid circular imports with cli.py)
_CLR_PRE   = "\033[1;32m"   # bold green
_CLR_BOLD  = "\033[1m"
_CLR_DIM   = "\033[2m"
_CLR_RESET = "\033[0m"
_CLR_WARN  = "\033[1;33m"   # bold yellow


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load_store() -> list[dict]:
    """Load the feedback JSON file, returning an empty list on any error."""
    if not os.path.exists(FEEDBACK_PATH):
        return []
    try:
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_store(store: list[dict]) -> None:
    try:
        with open(FEEDBACK_PATH, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2, ensure_ascii=False)
    except Exception:
        pass


def save_feedback(reply: str, note: str) -> None:
    """Persist one feedback entry."""
    store = _load_store()
    store.append({
        "ts":    datetime.utcnow().isoformat(),
        "reply": reply,
        "note":  note.strip(),
    })
    _save_store(store)


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

def load_feedback_notes(limit: int = _MAX_INJECT) -> Optional[str]:
    """
    Return the most recent *limit* feedback notes formatted as a prompt block,
    or None if no feedback has been saved yet.
    """
    store = _load_store()
    if not store:
        return None

    # Most recent entries first
    recent = store[-limit:][::-1]
    lines = []
    for entry in recent:
        lines.append(f'- "{entry["note"]}"')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive prompt
# ---------------------------------------------------------------------------

def maybe_ask_feedback(reply: str) -> None:
    """
    With probability _ASK_PROBABILITY, ask the user whether the reply was
    good and optionally collect written corrections.

    Called *after* the reply has been shown and copied.  Safe to call even if
    the reply contained an error — the caller should skip it in that case.
    """
    if random.random() > _ASK_PROBABILITY:
        return

    print(f"\n{_CLR_WARN}─── Quick feedback (optional) ───{_CLR_RESET}")
    print(f"{_CLR_DIM}Was that reply on-brand for you?{_CLR_RESET}  "
          f"{_CLR_BOLD}y{_CLR_RESET} / {_CLR_BOLD}n{_CLR_RESET} / "
          f"{_CLR_BOLD}f{_CLR_RESET}(eedback) / {_CLR_BOLD}skip{_CLR_RESET}")

    try:
        choice = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not choice or choice in {"y", "yes", "skip", "s"}:
        # Positive or skipped — nothing to store
        return

    # "n" or "f" or anything else → ask for written corrections
    print(f"\n{_CLR_DIM}What should be different? Describe the change or type an improved version:{_CLR_RESET}")
    print(f"{_CLR_DIM}(e.g. \"shorter\", \"don't say 'certainly'\", \"more like: nah bro cant make it\"){_CLR_RESET}")

    try:
        note = input("Correction: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not note:
        return

    save_feedback(reply, note)
    print(f"{_CLR_PRE}✅ Got it — I'll apply that to future replies.{_CLR_RESET}\n")
