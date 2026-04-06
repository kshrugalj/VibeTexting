# VibeTexting CLI 🎤

A powerful CLI tool to help you respond to text messages faster using AI-powered tone-based response generation. It can run locally with Ollama or via Groq's cloud API.

## Features

- 💻 **CLI Tool** - Generate replies directly from your terminal.
- 🏠 **Truly Local AI** - Support for Ollama to run 100% locally.
- 🎭 **Personal Vibe Mimicry** - Extracts your iMessage style to sound like *you*.
- 🎨 **5 Tone Options** - Casual, Professional, Funny, Friendly, Concise.
- 📋 **Clipboard Integration** - Auto-detect messages from your clipboard.
- 🛠️ **Developer Friendly** - Easy to install and extend.

## Project Structure

```
VibeTexting/
├── vibetext.py              # Main CLI Tool (Local/Cloud)
├── extract_imessage_vibe.py  # Mac-only script to learn your style from iMessage
├── pyproject.toml           # Python package configuration
├── backend/                 # FastAPI server (optional, used by mobile apps)
└── README.md
```

## Installation

You can install the VibeTexting CLI globally on your Mac/PC:

```bash
# Clone the repository
git clone https://github.com/kshrugalj/VibeTexting.git
cd VibeTexting

# Install as a local package
pip install -e .
```

## Quick Start

### 1. Using Cloud AI (Groq)

1. Get a free API key from [Groq Console](https://console.groq.com).
2. Create a `.env` file in the root directory:
   ```bash
   echo "GROQ_API_KEY=your_key_here" > .env
   ```
3. Run the CLI:
   ```bash
   vibetexting
   ```

### 2. Using Local AI (Ollama)

1. Install [Ollama](https://ollama.com).
2. Pull a model (e.g., Llama 3):
   ```bash
   ollama pull llama3
   ```
3. Run the CLI with the `--local` flag:
   ```bash
   vibetexting --local
   ```

### 3. Training on Your Style (Mac Only)

1. Run the extraction script:
   ```bash
   vibe-extract
   ```
2. **Note:** You will be prompted to grant "Full Disk Access" to Terminal (or your IDE) in *System Settings > Privacy & Security > Full Disk Access* to allow the script to read your iMessage database.
3. The script creates `my_vibe_profile.txt`.
4. Run `vibetexting` and it will automatically detect this file to mimic your personal texting style!

## Usage Options

```bash
vibetexting --help
```

| Argument | Description |
|----------|-------------|
| `--local` | Use local Ollama instead of Groq cloud API. |
| `--model` | Specify the Ollama model to use (default: `llama3`). |
| `--vibe`  | Path to a specific vibe profile text file. |

## Tone Options

| Tone | Use Case |
|------|----------|
| Casual | Friends, family, relaxed chats. |
| Professional | Work, business, or formal inquiries. |
| Funny | Jokes, playful banter, memes. |
| Friendly | Warm, supportive, and kind. |
| Concise | Quick acknowledgments and "to the point" replies. |

## How it Works

1. **Input Detection:** The tool automatically pulls the last text from your clipboard.
2. **Context Selection:** You can choose to provide a "Draft Reply" (what you *want* to say) to guide the AI.
3. **Tone Mapping:** Select one of the 5 tones to wrap your message.
4. **Vibe Mimicry:** If a `my_vibe_profile.txt` exists, the AI uses "Few-Shot Prompting" to match your specific vocabulary and sentence structure.
5. **Output:** The generated reply is printed to the terminal for you to copy.

## Contributing

Future plans include removing the copy-paste requirement and using screen-sharing/computer vision technology to detect messages automatically. 

Feel free to open issues or submit PRs!

## License

MIT License
