# VibeTexting CLI 🎤 (Version 1.0)

A powerful, 100% local AI tool to help you respond to text messages faster and more authentically. VibeTexting learns your unique texting "vibe" from your iMessage history and autonomously drafts replies that sound exactly like you. 

## Features

- 🏠 **Truly Local AI** - Powered by [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai). Run everything entirely on your own machine for complete privacy.
- 🤖 **Auto-Pilot Mode** - Let the AI take the wheel. VibeTexting can monitor specific chats, read incoming messages, wait a natural delay, and automatically send conversational replies.
- 🎭 **Personal Vibe Mimicry** - Uses your actual sent iMessages as few-shot training examples to match your vocabulary, capitalization, and punctuation habits.
- 🧠 **Smart Memories & Context** - Automatically retrieves relevant past context from your SQLite message history and groups multiple incoming unread messages together to provide accurate, context-aware replies.
- 🎯 **Conversation Goals** - Set a specific objective (e.g., "Ask them to hang out this weekend"), and the AI will naturally steer the conversation toward it.
- ⚡ **Interactive CLI** - Built with `prompt-toolkit` for a rich, colorized terminal experience complete with slash-command autocompletion dropdowns.
- 👥 **Group Chat Aware** - Full support for group threads, attributing messages to the correct participants.
- ⏱️ **Configurable Delays** - Set a custom delay before auto-responding to simulate natural typing speeds and avoid looking like a bot.

## Installation

### 1. Prerequisites

1.  **macOS**: VibeTexting relies on Apple's `chat.db` (iMessage) and AppleScript to read and send messages.
2.  **Ollama** or **LM Studio**:
    - [Download Ollama](https://ollama.com) and pull a model (e.g., `ollama pull llama3`).
    - Or use LM Studio and start the Local Inference Server (default port: 1234).

### 2. Install VibeTexting

```bash
# Clone the repository
git clone https://github.com/kshrugalj/VibeTexting.git
cd VibeTexting

# Install the package locally
pip install -e .
```

*Note: You will be prompted by macOS to grant "Full Disk Access" to your Terminal (or IDE) to allow VibeTexting to read your iMessage `chat.db` database.*

## Quick Start

### 1. Extract Your Vibe Profile

Before generating responses, you need to teach the AI how you text. Run the extraction script to sample your recent sent messages:

```bash
vibe-extract
```

This creates a `my_vibe_profile.txt` file containing your unique style. 

### 2. Setup Default Configuration

Run the setup wizard to configure your preferred LLM backend and default vibe profile:

```bash
vibetexting --setup
```

### 3. Run the CLI

Start the interactive generator:

```bash
vibetexting
```

## How Auto-Pilot Works

When you run `/auto`, VibeTexting runs a background polling loop checking your iMessage database every 5 seconds. 

1. **Detection:** It detects new incoming messages.
2. **Delay:** It waits for your configured `/delay` time.
3. **Prompt Generation:** It builds a strict, optimized prompt combining your vibe profile, chat history, conversation goal, and memory context.
4. **Sending:** It automatically sends the AI-generated reply directly through the macOS Messages app using AppleScript.

## Project Structure (V1)

```
VibeTexting/
├── vibetexting/             # Core package
│   ├── cli.py               # Main CLI loop & Auto-Pilot logic
│   ├── llm.py               # API integrations for Ollama/LM Studio
│   ├── database.py          # iMessage SQLite extraction & Memories mapping
│   ├── prompts.py           # Intelligent prompt engineering & constraints
│   ├── config.py            # User configuration management
│   └── utils.py             # AppleScript sending & clipboard helpers
├── extract_imessage_vibe.py # Few-shot extraction script
├── pyproject.toml           # Build configuration & dependencies
└── README.md
```

## License

MIT License
