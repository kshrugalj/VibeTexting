import asyncio
import threading
import os
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .providers.imessage import IMessageProvider
from .llm import call_local_llm
from .config import load_user_config
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Ghost Dashboard API")

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Global state for background Auto-Pilot tasks
# {chat_id: {"task": asyncio.Task | None, "goal": str, "active": bool}}
autopilot_sessions = {}
autopilot_lock = threading.Lock()
AUTOPILOT_EVENT_LIMIT = 12
AUTOPILOT_TRANSCRIPT_LIMIT = 16

class MessageRequest(BaseModel):
    text: str
    recipient_label: str
    chat_guid: Optional[str] = None

class AutopilotToggleRequest(BaseModel):
    chat_id: int
    chat_filter: str
    goal: str
    enabled: bool

def _record_autopilot_event(chat_id: int, event_type: str, message: str):
    with autopilot_lock:
        session = autopilot_sessions.get(chat_id)
        if not session:
            return
        events = session.setdefault("events", [])
        events.append({"type": event_type, "message": message})
        if len(events) > AUTOPILOT_EVENT_LIMIT:
            del events[:-AUTOPILOT_EVENT_LIMIT]

def _record_autopilot_transcript(chat_id: int, speaker: str, message: str):
    cleaned = " ".join((message or "").split()).strip()
    if not cleaned:
        return

    with autopilot_lock:
        session = autopilot_sessions.get(chat_id)
        if not session:
            return
        transcript = session.setdefault("transcript", [])
        transcript.append({"speaker": speaker, "message": cleaned[:240]})
        if len(transcript) > AUTOPILOT_TRANSCRIPT_LIMIT:
            del transcript[:-AUTOPILOT_TRANSCRIPT_LIMIT]

def _build_autopilot_summary(session: Dict) -> str:
    transcript = session.get("transcript", [])
    if not transcript:
        return "No conversation has happened yet since Auto was engaged."

    incoming = [item["message"] for item in transcript if item.get("speaker") == "them"]
    replies = [item["message"] for item in transcript if item.get("speaker") == "auto"]

    summary_parts = []
    if incoming:
        latest_topics = "; ".join(incoming[-3:])
        summary_parts.append(f"They talked about {latest_topics}.")
    if replies:
        latest_replies = "; ".join(replies[-2:])
        summary_parts.append(f"Auto replied with {latest_replies}.")

    if not summary_parts:
        return "Auto has been engaged, but there is not enough conversation yet to summarize."
    return " ".join(summary_parts)

@app.get("/api/chats")
async def get_chats():
    provider = IMessageProvider()
    return provider.get_recent_chats(limit=50)

@app.get("/api/chats/{chat_id}/history")
async def get_history(chat_id: int, chat_filter: str, limit: int = 20):
    provider = IMessageProvider()
    history, total, label, is_group, context, cid, guid, last_is_from_me = provider.load_history(
        chat_filter, limit=limit, auto_select=True, chat_id=chat_id
    )
    return {
        "history": history,
        "total_count": total,
        "label": label,
        "is_group": is_group,
        "chat_guid": guid,
        "last_is_from_me": last_is_from_me
    }

@app.post("/api/chats/{chat_id}/send")
async def send_message(chat_id: int, req: MessageRequest):
    provider = IMessageProvider()
    success = provider.send_message(req.recipient_label, req.text, chat_id=req.chat_guid)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send message")
    return {"status": "success"}

@app.get("/api/autopilot/status")
async def get_autopilot_status():
    with autopilot_lock:
        return {
            cid: {
                "active": data["active"],
                "goal": data["goal"],
                "summary": _build_autopilot_summary(data),
                "events": data.get("events", []),
                "transcript": data.get("transcript", []),
            }
            for cid, data in autopilot_sessions.items()
            if data.get("active")
        }

def _load_vibe_content(vibe_path: Optional[str]) -> str:
    if vibe_path and os.path.exists(vibe_path):
        with open(vibe_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def _maybe_generate_autopilot_reply(
    provider: IMessageProvider,
    args,
    chat_id: int,
    chat_filter: str,
    goal: str,
) -> bool:
    history_full, _, label, _, context, _, guid, last_is_me = provider.load_history(
        chat_filter, limit=20, auto_select=True, chat_id=chat_id
    )

    if not history_full or last_is_me:
        return False

    from .prompts import build_prompt

    lines = history_full.strip().split("\n")
    if not lines:
        return False

    last_line = lines[-1]
    original_msg = last_line.split(": ", 1)[1] if ": " in last_line else last_line
    _record_autopilot_event(chat_id, "incoming", f"Incoming: {original_msg[:120]}")
    _record_autopilot_transcript(chat_id, "them", original_msg)
    vibe_content = _load_vibe_content(args.vibe)

    prompt = build_prompt(
        original_msg,
        vibe_content,
        history_full,
        label,
        context,
        args.name,
        None,
        None,
        None,
        goal,
    )

    reply = call_local_llm(prompt, args.model, args.backend)
    if "Error" in reply:
        _record_autopilot_event(chat_id, "error", "Reply generation failed.")
        return False

    provider.send_message(label, reply, chat_id=guid)
    _record_autopilot_event(chat_id, "reply", f"Sent: {reply[:120]}")
    _record_autopilot_transcript(chat_id, "auto", reply)
    return True

async def _autopilot_loop(chat_id: int, chat_filter: str, goal: str):
    """Background polling loop for a specific chat."""
    provider = IMessageProvider()
    try:
        # Initial state
        last_history, _, _, _, _, _, _, _ = provider.load_history(
            chat_filter, limit=1, auto_select=True, chat_id=chat_id
        )

        config = load_user_config()

        class Args:
            model = config.get("model")
            backend = config.get("backend")
            vibe = config.get("vibe")
            name = config.get("name")
            history_limit = 20
            delay = 0

        args = Args()
        _record_autopilot_event(chat_id, "status", "Auto engaged.")

        # If the latest current message is already from the other person,
        # respond immediately instead of waiting for a future poll change.
        responded_immediately = _maybe_generate_autopilot_reply(provider, args, chat_id, chat_filter, goal)
        if not responded_immediately:
            _record_autopilot_event(chat_id, "status", "Monitoring for new incoming messages.")
        last_history, _, _, _, _, _, _, _ = provider.load_history(
            chat_filter, limit=1, auto_select=True, chat_id=chat_id
        )

        while True:
            with autopilot_lock:
                if not autopilot_sessions.get(chat_id, {}).get("active"):
                    break

            await asyncio.sleep(5)

            try:
                current_history, _, label, _, context, _, guid, _ = provider.load_history(
                    chat_filter, limit=1, auto_select=True, chat_id=chat_id
                )

                if current_history != last_history:
                    _maybe_generate_autopilot_reply(provider, args, chat_id, chat_filter, goal)
                    last_history = current_history
            except Exception as e:
                _record_autopilot_event(chat_id, "error", f"Monitor error: {str(e)[:120]}")
                print(f"Error in autopilot loop for {chat_id}: {e}")
    except asyncio.CancelledError:
        pass
    finally:
        with autopilot_lock:
            session = autopilot_sessions.get(chat_id)
            if session and not session.get("active"):
                autopilot_sessions.pop(chat_id, None)
            elif session:
                session["task"] = None

@app.post("/api/autopilot/toggle")
async def toggle_autopilot(req: AutopilotToggleRequest):
    chat_id = req.chat_id
    
    with autopilot_lock:
        if req.enabled:
            existing = autopilot_sessions.get(chat_id)
            if existing and existing.get("active"):
                return {"status": "already_active"}

            task = asyncio.create_task(_autopilot_loop(chat_id, req.chat_filter, req.goal))
            autopilot_sessions[chat_id] = {
                "active": True,
                "goal": req.goal,
                "task": task,
                "events": [{"type": "status", "message": "Auto starting..."}],
                "transcript": [],
            }
        else:
            existing = autopilot_sessions.get(chat_id)
            if existing:
                task = existing.get("task")
                existing["active"] = False
                if task and not task.done():
                    task.cancel()
                autopilot_sessions.pop(chat_id, None)
                
    return {"status": "success", "enabled": req.enabled}

# Mount the static files from the React build directory (Fallback)
# Define this LAST so it doesn't swallow /api routes
server_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(server_dir)
web_dist_path = os.path.join(project_root, "vibetexting-web", "dist")

if os.path.exists(web_dist_path):
    print(f"🚀 Serving Ghost Dashboard from: {web_dist_path}")
    app.mount("/", StaticFiles(directory=web_dist_path, html=True), name="static")
else:
    print(f"❌ Error: Web build directory not found at {web_dist_path}")
    print("   Please run: cd vibetexting-web && npm run build")
