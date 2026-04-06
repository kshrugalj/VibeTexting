# VibeTexting CLI 🎤

A powerful CLI tool to help you respond to text messages faster using AI-powered style-matched response generation. It can run locally with Ollama or via Groq's cloud API.

## Features

- 🏠 **Truly Local AI** - Powered by [Ollama](https://ollama.com) to run everything on your machine.
- 🎭 **Personal Vibe Mimicry** - Extracts your iMessage style to sound like *you*.
- 🎨 **Personal Style Matching** - Uses your sent messages as examples.
- 📋 **Clipboard Integration** - Auto-detect messages from your clipboard.
- 🧵 **Chat History Context** - Loads recent iMessage history for the person you're texting, with a Contacts.app fallback for saved names.
- 🛠️ **Developer Friendly** - Easy to install and extend.

## Project Structure

```
VibeTexting/
├── vibetext.py              # Main CLI Tool (Ollama-powered)
├── extract_imessage_vibe.py  # Mac-only script to learn your style from iMessage
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

### 2. Install VibeTexting

You can install the CLI globally on your Mac/PC:

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

### 2. Training on Your Style (Mac Only)

1. Run the extraction script:
   ```bash
   vibe-extract
   ```
2. **Note:** You will be prompted to grant "Full Disk Access" to Terminal (or your IDE) in *System Settings > Privacy & Security > Full Disk Access* to allow the script to read your iMessage database.
3. The script creates `my_vibe_profile.txt`.
4. It also exports recent chat history to `my_chat_history.txt`.
4. Run `vibetexting` and it will automatically detect this file to mimic your personal texting style!

### Pulling Chat History from Messages

Use `vibe-extract` with optional filters when you want to mimic one specific conversation style:

```bash
# Default: sample your sent style + export recent mixed chat history
vibe-extract

# Pull history for one person/chat name/number
vibe-extract --chat "mom"

# Export more context into a custom file
vibe-extract --history-limit 1000 --history-out mom_history.txt --chat "+1415"
```

Useful flags:

| Argument | Description |
|----------|-------------|
| `--chat` | Filter by contact handle (phone/email) or chat display name. |
| `--limit` | Number of your sent messages sampled for `my_vibe_profile.txt` (default: `150`). |
| `--history-limit` | Number of recent messages exported for chat history (default: `300`). |
| `--history-full` | Export the full chat history instead of a limited slice. |
| `--history-out` | Output file for chat history export (default: `my_chat_history.txt`). |

## Usage Options

```bash
vibetexting --help
```

| Argument | Description |
|----------|-------------|
| `--model` | Specify the Ollama model to use (default: `llama3`). |
| `--vibe`  | Path to a specific vibe profile text file. |
| `--chat` | Contact first name, last name, phone number, or email to load recent chat history for. |
| `--history-limit` | Number of recent messages to include from that chat (default: `20`). |

## How it Works

1. **Input Detection:** The tool automatically pulls the last text from your clipboard.
2. **Chat Lookup:** You can provide a contact first name, last name, phone number, or email so the tool loads recent iMessage history for that person, and it will try Contacts.app if Messages only stores a number or email.
3. **Vibe Mimicry:** If a `my_vibe_profile.txt` exists, the AI uses "Few-Shot Prompting" to match your specific vocabulary and sentence structure.
4. **Output:** The generated reply is printed to the terminal for you to copy.

## Contributing

Future plans include removing the copy-paste requirement and using screen-sharing/computer vision technology to detect messages automatically. 

Feel free to open issues or submit PRs!

## License

MIT License
