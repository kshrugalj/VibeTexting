# VibeTexting CLI 🎤 (V2.0)

VibeTexting V2.0 is a professional-grade, 100% local AI messaging assistant. Re-engineered for scale and cross-platform support, it transforms how you interact with messages by mimicking your personal "vibe" autonomously.

> **Looking for Version 1?** See [README_V1.md](./README_V1.md) for the original documentation.

## What's New in V2.0 🚀

### 🔌 Decoupled Provider Architecture
VibeTexting is no longer just for iMessage. The core engine is now completely abstracted.
- **Providers:** A new plug-and-play system for different platforms.
- **Scalable:** Built to easily add WhatsApp, Signal, or Web-based messaging in future updates.

### ⏳ Human-Centric "Natural Delay"
Auto-Pilot is no longer a simple timer.
- **Dynamic Typing:** AI calculates a realistic typing delay based on the character count of the generated response.
- **Anti-Bot Logic:** Simulates a real person "thinking" and "typing" to maintain social authenticity.

### 🎭 Dynamic Vibe Switching
Your AI now adapts its personality on the fly.
- **Context Aware:** Automatically swaps between different vibe profiles (e.g., `vibe_pro.txt` vs `vibe_casual.txt`) based on the recipient's identity in your config.

### ⚡ Automated LLM Lifecycle
No more manual server management.
- **Zero-Config Startup:** The CLI automatically checks for, matches, and starts your local LLM server (LM Studio) upon entry.
- **Auto-Cleanup:** Gracefully shuts down background servers when you exit the CLI.
- **Smart Matching:** Automatically handles model ID resolution (e.g., matching "gemma" to your specific local instance).

---

## Core Features

- 🏠 **Truly Local AI** - Powered by [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai). Complete privacy, zero data leaves your machine.
- 🤖 **V2.0 Auto-Pilot** - Autonomous monitoring, intelligent grouping of incoming messages, and natural-timed replies.
- 🎭 **Vibe Mimicry** - High-fidelity style imitation using few-shot learning from your actual sent messages.
- 🧠 **Semantic Memories** - Intelligent retrieval of past conversation context to ensure replies are grounded in reality.
- 🎯 **Conversational Goals** - Tell the AI what you want to achieve (e.g., "Schedule a meeting"), and it will steer the talk naturally.

## Installation

### 1. Prerequisites
- **macOS** (currently supports iMessage via AppleScript).
- **Ollama** or **LM Studio** (with the `lms` CLI tool installed).

### 2. Setup
```bash
git clone https://github.com/kshrugalj/VibeTexting.git
cd VibeTexting
pip install -e .

# Initial setup
vibe-extract
vibetexting --setup
```

## Project Architecture (V2.0)

```
VibeTexting/
├── vibetexting/
│   ├── providers/           # Platform-specific connectors (iMessage, WhatsApp, etc.)
│   ├── cli.py               # Human-in-the-loop & Auto-Pilot loop
│   ├── llm.py               # Universal LLM interface & server lifecycle
│   ├── database.py          # Data extraction & Memory engine
│   ├── prompts.py           # Vibe-matching prompt engineering
│   └── config.py            # Business-tier configuration
├── PROJECT_PROFILE.md       # Architectural DNA & Project Tier
└── README.md
```

## V2.0 Roadmap

- [x] **Semantic Memory (RAG 2.0)**: Transitioned from SQL keywords to Local Vector Embeddings (ChromaDB).
- [x] **Multi-Modal Support**: Vision model integration for describing image/meme attachments.
- [x] **Ghost Dashboard**: A local Web Dashboard (FastAPI/React) for batch-managing multiple threads.
- [x] **Contact Intelligence**: Native macOS Contacts sync for relationship identification.

## License
MIT License
