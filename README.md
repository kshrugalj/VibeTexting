# VibeTexting CLI 🎤

A powerful, 100% local AI tool to help you respond to text messages faster using style-matched response generation. VibeTexting learns your unique texting "vibe" from your iMessage history and drafts replies that sound exactly like you.

## New Features (v0.1.0)

- 🤖 **Auto-Pilot Mode** - Automatically monitors a specific chat and sends replies based on your style and goals.
- 🎯 **Conversation Goals** - Set a specific objective (e.g., "Ask them to hang out this weekend") and the AI will steer the conversation towards it.
- 🧠 **Smart Memories (RAG)** - Automatically retrieves relevant past context from your message history to provide more accurate and personalized replies.
- ⚡ **Gemma Auto-Start** - Automatically manages LM Studio servers for Gemma models via the `lms` CLI.
- 👥 **Group Chat Aware** - Full support for group threads with participant-aware history and context.

## Core Features

- 🏠 **Truly Local AI** - Powered by [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai) to run everything on your machine.
- 🎭 **Personal Vibe Mimicry** - Extracts your iMessage style to sound like *you*.
- 🎨 **Personal Style Matching** - Uses your sent messages as few-shot examples.
- 📋 **Clipboard Integration** - Auto-detect messages from your clipboard.
- 🧵 **Chat History Context** - Loads iMessage conversations with Contacts.app fallback for names.
- 🛠️ **Developer Friendly** - Easy to install and extend.

## Project Structure

```
VibeTexting/
├── vibetexting/             # Core package
│   ├── cli.py               # Main CLI entry point
│   ├── llm.py               # Backend integration (Ollama/LM Studio)
│   ├── database.py          # iMessage/SQLite integration & Memories
│   ├── prompts.py           # Intelligent prompt engineering
│   └── ...
├── vibetext.py              # Convenient wrapper script
├── extract_imessage_vibe.py  # Mac-only script to learn your style
├── pyproject.toml           # Python package configuration
└── README.md
```

## Installation

### 1. Install Prerequisites

1.  **Ollama**: Download and install from [ollama.com](https://ollama.com).
2.  **Pull a Model**: By default, VibeTexting uses `llama3`.
    ```bash
    ollama pull llama3
    ```
3.  **Optional: LM Studio**: If using LM Studio, install the `lms` CLI for automatic server management.

### 2. Install VibeTexting

```bash
# Clone the repository
git clone https://github.com/kshrugalj/VibeTexting.git
cd VibeTexting

# Install as a local package
pip install -e .
```

## Quick Start

### 1. Run the CLI

Start the generator by simply running:
```bash
vibetexting
```

### 1a. Set Up Your Defaults

Run the setup command once to create your saved user profile:

```bash
vibetexting --setup
```

This writes `~/.vibetexting.json` and stores your name, vibe file, and optional default recipient mapping.

### 2. Training on Your Style (Mac Only)

1. Run the extraction script:
   ```bash
   vibe-extract
   ```
2. **Note:** You will be prompted to grant "Full Disk Access" to Terminal (or your IDE) in *System Settings > Privacy & Security > Full Disk Access*.
3. The script creates `my_vibe_profile.txt` (your style) and `my_chat_history.txt` (recent context).

**💡 Pro Tip: Excluding AI Messages**
If you've been using Auto-Pilot, your iMessage history will contain messages written by the AI. To ensure you only train on *your* real messages, use the cutoff flag:
```bash
vibe-extract --cutoff-date 2024-01-01
```
This ensures your "vibe" profile stays authentic to your actual writing style.

## Interactive Commands

Once inside the `vibetexting` CLI, you can use several slash-commands:

| Command | Description |
|----------|-------------|
| `/chat [name]` | Switch recipient and load their history. |
| `/groups` | List and switch to recent group chats. |
| `/auto` | **Enter Auto-Pilot mode** (monitors and replies automatically). |
| `/goal [text]` | Set a conversation goal (steers AI automatically). |
| `/models` | List all available local models (Ollama & LM Studio). |
| `/model [name]` | Switch to a specific model on the fly. |
| `/limit [num]` | Change message history context limit. |
| `/full` | Use the WHOLE conversation as context. |
| `/vibe [path]` | Switch to a different vibe profile file. |
| `/paste` | Use text from clipboard as the message to reply to. |
| `/help` | Show the help menu. |
| `exit` / `quit` | Exit VibeTexting. |

## Auto-Pilot & Goals

Auto-Pilot (`/auto`) allows VibeTexting to run in the background. It polls your iMessage database every 5 seconds for new incoming messages and automatically drafts and sends a reply.

You can combine this with `/goal` to have the AI autonomously navigate a conversation toward a specific outcome without you needing to manually prompt it for every message.

## How it Works

1. **Input Detection:** Automatically pulls the last text from your clipboard or monitors iMessage in Auto-Pilot.
2. **Chat Lookup:** Intelligent matching for contact names, phone numbers, or group thread titles.
3. **Context Retrieval (Memories):** Searches your past messages for keywords in the current message to provide the AI with relevant historical context ("What did we talk about last time?").
4. **Intent Check:** For complex messages, it pauses to ask for your intent or raw facts (in `suggest` mode) before drafting.
5. **Vibe Mimicry:** Uses "Few-Shot Prompting" with your extracted style to ensure the reply sounds authentic.
6. **Output:** In manual mode, it copies the reply to your clipboard. In Auto-Pilot, it sends it automatically via AppleScript.

## Contributing

Feel free to open issues or submit PRs! Current roadmap includes:
- [ ] Improved RAG with vector embeddings.
- [ ] Support for image/mms attachments.
- [ ] Web-based UI.

## License

MIT License
