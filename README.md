# VibeTexting CLI 🎤 (V2.0)

VibeTexting V2.0 is a professional-grade, 100% local AI messaging assistant. Re-engineered for scale and cross-platform support, it transforms how you interact with messages by mimicking your personal "vibe" autonomously.

> **Looking for Version 1?** See [README_V1.md](./README_V1.md) for the original documentation.

## What's New in V2.0 🚀

### 🔌 Decoupled Provider Architecture
VibeTexting is no longer just for iMessage. The core engine is abstracted behind a plug-and-play provider system, and **WhatsApp support now ships** alongside iMessage (Signal coming soon).

### 👻 Ghost Dashboard (V2.0 Mission Control)
A local Web Dashboard built with **FastAPI** and **React** for batch-managing multiple threads and monitoring Auto-Pilot status in real-time.

### 🧠 Semantic Memory (RAG 2.0)
Transitioned from SQL keywords to **Local Vector Embeddings (ChromaDB)**. The AI now retrieves relevant past context using semantic similarity, ensuring replies are grounded in your actual history.

### 👁️ Multi-Modal Vision Support
Integrated vision model support (LLaVA via Ollama) to describe incoming image and meme attachments, allowing the AI to "see" and respond to visual context.

### 👥 Contact Intelligence
Native macOS Contacts sync for relationship identification and improved name resolution.

---

## Core Features

- 🏠 **Truly Local AI** - Powered by [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai). Complete privacy, zero data leaves your machine.
- 🤖 **V2.0 Auto-Pilot** - Autonomous monitoring, intelligent grouping of incoming messages, and human-like typing delays.
- 🎭 **Vibe Mimicry** - High-fidelity style imitation using few-shot learning from your actual sent messages.
- 🎯 **Conversational Goals** - Set a specific objective (e.g., "Schedule a meeting"), and the AI will steer the talk naturally.

## Installation

### 1. Prerequisites
- **macOS** (supports iMessage via AppleScript).
- **Ollama** (for RAG and Vision) or **LM Studio**.
- **Node.js 18+** (only for WhatsApp support).
- **Full Disk Access**: Terminal/IDE requires this to read `chat.db`.

### 2. Setup
```bash
# Clone and install
git clone https://github.com/kshrugalj/VibeTexting.git
cd VibeTexting
pip install -e .

# Extract your "vibe" profile
vibe-extract

# Initial configuration wizard
vibetexting --setup
```

## How to Run

### 1. Interactive CLI Mode
Start the main CLI to chat and generate replies manually:
```bash
vibetexting
```

### 2. Ghost Dashboard (Web UI)
Launch the local web server to manage chats via a dashboard:
```bash
# Start the FastAPI server
uvicorn vibetexting.server:app --reload --port 8000
```
Then visit `http://localhost:8000` in your browser.

### 3. Auto-Pilot Mode
Inside the CLI, use the `/auto` command to let the AI monitor and respond to a specific contact automatically.

---

## WhatsApp Support

WhatsApp is linked as a companion device through a small local bridge (`vibetexting-whatsapp/`, Node + Baileys). Chats, media and link credentials stay on this machine; the bridge only listens on `127.0.0.1`.

```bash
# one-time: install the bridge dependencies
cd vibetexting-whatsapp && npm install && cd ..

# use WhatsApp for this run
vibetexting --provider whatsapp
```

On the first run a QR code is printed. In WhatsApp open **Settings → Linked devices → Link a device** and scan it. The link is stored in `~/.vibetexting/whatsapp_auth/` and reused afterwards.

To make WhatsApp the default platform, add it to your config:

```json
{
  "provider": "whatsapp"
}
```

How it fits together:

- The bridge starts automatically when the provider is selected. Logs: `~/.vibetexting/whatsapp_bridge.log`.
- Recent messages are cached in `~/.vibetexting/whatsapp_messages.jsonl`; downloaded images (used for vision) in `~/.vibetexting/whatsapp_media/`.
- The dashboard (`vibetexting --dashboard`) follows the same provider setting, so Auto-Pilot works on WhatsApp threads too.
- `/wrapped` and ChromaDB semantic memory still read the iMessage database; WhatsApp memory search is keyword-based for now.
- If the phone unlinks this device, remove `~/.vibetexting/whatsapp_auth/` and scan a new QR code.

---

## CLI Commands

| Command | Description |
|----------|-------------|
| `/chat [name]` | Switch recipient and load their history. |
| `/groups` | List and switch to recent group chats. |
| `/auto` | Enter Auto-Pilot mode. |
| `/goal [text]` | Set a goal for the AI to steer toward. |
| `/models` | List available local LLM models. |
| `/vibe [path]` | Switch to a different vibe profile. |
| `/help` | Show all available commands. |

### Platform selection

| Flag / setting | Description |
|----------------|-------------|
| `--provider imessage` | Use iMessage for this run (default). |
| `--provider whatsapp` | Use WhatsApp for this run. |
| `"provider"` in `~/.vibetexting.json` | Default platform when no flag is passed. |

## Project Architecture

```
VibeTexting/
├── vibetexting/
│   ├── providers/     # Platform connectors (iMessage, etc.)
│   ├── server.py      # FastAPI backend for Ghost Dashboard
│   ├── database.py    # ChromaDB (RAG) & SQLite logic
│   ├── vision.py      # Image analysis via local vision models
│   ├── cli.py         # Main interactive loop
│   └── prompts.py     # Vibe-matching prompt engineering
├── vibetexting-whatsapp/ # Local WhatsApp bridge (Node + Baileys)
├── vibetexting-web/   # React Dashboard (Vite + Tailwind)
└── PROJECT_PROFILE.md
```

## License
MIT License
