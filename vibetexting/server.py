import os
import asyncio
import threading
from typing import List, Dict, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from .database import load_recent_chat_history, list_recent_group_chats
from .providers.imessage import IMessageProvider
from .llm import call_local_llm
from .config import load_user_config, merge_runtime_settings
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
# {chat_id: {"task": Task, "goal": str, "active": bool}}
autopilot_sessions = {}
autopilot_lock = threading.Lock()

class MessageRequest(BaseModel):
    text: str
    recipient_label: str
    chat_guid: Optional[str] = None

class AutopilotToggleRequest(BaseModel):
    chat_filter: str
    goal: str
    enabled: bool

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
        return {cid: {"active": data["active"], "goal": data["goal"]} for cid, data in autopilot_sessions.items()}

async def _autopilot_loop(chat_id: int, chat_filter: str, goal: str):
    """Background polling loop for a specific chat."""
    provider = IMessageProvider()
    # Initial state
    last_history, _, _, _, _, _, _, _ = provider.load_history(chat_filter, limit=1, auto_select=True, chat_id=chat_id)
    
    config = load_user_config()
    # Dummy args for merge_runtime_settings
    class Args:
        model = config.get("model")
        backend = config.get("backend")
        vibe = config.get("vibe")
        name = config.get("name")
        history_limit = 20
        delay = 0
    args = Args()

    while True:
        with autopilot_lock:
            if not autopilot_sessions.get(chat_id, {}).get("active"):
                break
        
        await asyncio.sleep(5)
        
        try:
            current_history, _, label, is_group, context, cid, guid, _ = provider.load_history(
                chat_filter, limit=1, auto_select=True, chat_id=chat_id
            )
            
            if current_history != last_history:
                # New message detected
                history_full, _, _, _, context, _, _, last_is_me = provider.load_history(
                    chat_filter, limit=20, auto_select=True, chat_id=chat_id
                )
                
                if not last_is_me:
                    from .prompts import build_prompt
                    from .vision import describe_image
                    
                    # Basic extraction of last incoming message for prompt building
                    lines = history_full.strip().split("\n")
                    last_line = lines[-1]
                    original_msg = last_line.split(": ", 1)[1] if ": " in last_line else last_line
                    
                    vibe_content = ""
                    if os.path.exists(args.vibe):
                        with open(args.vibe, "r") as f:
                            vibe_content = f.read()

                    prompt = build_prompt(
                        original_msg, vibe_content, history_full, label, context, args.name,
                        None, None, None, goal
                    )
                    
                    reply = call_local_llm(prompt, args.model, args.backend)
                    if "Error" not in reply:
                        provider.send_message(label, reply, chat_id=guid)
                
                last_history = current_history
        except Exception as e:
            print(f"Error in autopilot loop for {chat_id}: {e}")

@app.post("/api/autopilot/toggle")
async def toggle_autopilot(req: AutopilotToggleRequest, background_tasks: BackgroundTasks):
    # This is a placeholder chat_id resolution - in production we'd use the integer ID
    # For now, we'll try to find the ID via resolve_chat_matches
    from .database import resolve_chat_matches
    matches = resolve_chat_matches(req.chat_filter, auto_select=True)
    if not matches:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat_id = matches[0][1]
    
    with autopilot_lock:
        if req.enabled:
            if chat_id in autopilot_sessions and autopilot_sessions[chat_id]["active"]:
                return {"status": "already_active"}
            
            autopilot_sessions[chat_id] = {"active": True, "goal": req.goal}
            background_tasks.add_task(_autopilot_loop, chat_id, req.chat_filter, req.goal)
        else:
            if chat_id in autopilot_sessions:
                autopilot_sessions[chat_id]["active"] = False
                
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
