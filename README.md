# VibeTexting CLI 🎤

A **100% Local** AI-powered CLI tool to help you respond to text messages faster using tone-based response generation. Your messages never leave your computer, ensuring complete privacy.

## Features

- 🏠 **Truly Local AI** - Powered by [Ollama](https://ollama.com) to run everything on your machine.
- 🎭 **Personal Vibe Mimicry** - Extracts your iMessage style to sound like *you*.
- 🎨 **5 Tone Options** - Casual, Professional, Funny, Friendly, Concise.
- 📋 **Clipboard Integration** - Auto-detect messages from your clipboard.
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
4. Run `vibetexting` again, and it will automatically detect this file to mimic your personal texting style!

## Usage Options

```bash
vibetexting --help
```

| Argument | Description |
|----------|-------------|
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
4. **Vibe Mimicry:** If a `my_vibe_profile.txt` exists, the AI uses "Few-Shot Prompting" to match your specific vocabulary, sentence structure, and punctuation habits.
5. **Output:** The generated reply is printed to the terminal and automatically copied back to your clipboard.

## Contributing

Future plans include removing the copy-paste requirement and using screen-sharing/computer vision technology to detect messages automatically. 

Feel free to open issues or submit PRs!

## License

MIT License
