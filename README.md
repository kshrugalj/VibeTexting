# VibeTexting 🎤

An iOS app that helps you respond to text messages faster using AI-powered tone-based response generation.

![iOS](https://img.shields.io/badge/iOS-16.0+-blue)
![Swift](https://img.shields.io/badge/Swift-5.9-orange)
![Platform](https://img.shields.io/badge/Platform-iOS-lightgrey)

## Features

- 🎤 **Voice Input** - Dictate your reply using iOS Speech framework
- 💻 **CLI Tool** - Generate replies directly from your terminal
- 🏠 **Truly Local AI** - Support for Ollama to run 100% locally
- 🎭 **Personal Vibe Mimicry** - Extracts your iMessage style to sound like *you*
- 🎨 **5 Tone Options** - Casual, Professional, Funny, Friendly, Concise
- 📋 **Clipboard Integration** - Auto-detect messages from clipboard on iOS & Mac
- 🚀 **Native UX** - SwiftUI and Python CLI flows

## Project Structure

```
VibeTexting/
├── vibetext.py              # CLI Tool (Local/Cloud)
├── extract_imessage_vibe.py  # Mac-only script to learn your style
├── pyproject.toml           # Python package configuration
├── iOS/                     # Swift/SwiftUI iOS App
├── backend/                 # FastAPI server for iOS App
└── README.md
```

## CLI Installation (Open Source Friendly)

You can install the VibeTexting CLI globally on your Mac/PC:

```bash
# Clone the repository
git clone https://github.com/yourusername/VibeTexting.git
cd VibeTexting

# Install as a local package
pip install -e .
```

Now you can run the following commands from anywhere:
- `vibetexting` - Start the generator
- `vibe-extract` - (Mac only) Learn your texting style from iMessage

### Running Locally with Ollama

1. Install [Ollama](https://ollama.com)
2. Pull a model: `ollama pull llama3`
3. Run the CLI: `vibetexting --local`

### Training the AI on your style (Mac Only)

1. Run `vibe-extract`.
2. (Follow the prompt to grant "Full Disk Access" to Terminal in System Settings).
3. The script creates `my_vibe_profile.txt`.
4. Run `vibetexting --local` and it will automatically load your profile to mimic you!

## Quick Start

### 1. Set Up Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file with your Groq API key
echo "GROQ_API_KEY=your_key_here" > .env

# Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Get a Groq API key: https://console.groq.com

### 2. Set Up iOS App

```bash
cd iOS/VibeTexting
open VibeTexting.xcodeproj
```

In Xcode:
1. Select your development team
2. Update `APIManager.swift` with your backend URL
3. Build and run (⌘R)

### 3. Use the App

1. Copy a text message to clipboard
2. Open VibeTexting - it detects the clipboard content
3. (Optional) Tap mic to dictate your draft reply
4. Select a tone
5. Tap "Generate Reply"
6. Copy or share the AI-generated response

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health check |
| `/generate-reply` | POST | Generate AI response |
| `/generate-alternatives` | POST | Get 3 alternative phrasings |

## Tone Options

| Tone | Icon | Use Case |
|------|------|----------|
| Casual | 😎 | Friends, family |
| Professional | 💼 | Work, business |
| Funny | 😄 | Jokes, playful chats |
| Friendly | 🤗 | Warm, supportive |
| Concise | ⚡ | Quick acknowledgments |

## Permissions Required

- **Speech Recognition** - For voice-to-text input
- **Clipboard Access** - To detect incoming messages

## UX Best Practices

✅ **Minimal Taps** - 1-2 taps to get a reply  
✅ **Visual Feedback** - Recording & loading states  
✅ **Clear Icons** - Tone indicators with emoji  
✅ **Error Handling** - Helpful error messages  
✅ **Large Targets** - Easy-to-tap buttons  

## Roadmap

- [ ] Share Sheet extension for direct messaging integration
- [ ] Custom tone presets
- [ ] Multiple language support
- [ ] Widget for quick access
- [ ] Apple Watch companion
- [ ] End-to-end encryption for privacy

## Tech Stack

**iOS App:**
- SwiftUI
- iOS Speech Framework (SFSpeechRecognizer)
- URLSession for networking
- UserDefaults for local storage

**Backend:**
- FastAPI
- Uvicorn (ASGI server)
- Groq API (Llama 3.1)
- httpx for async HTTP

## Development

### Running Tests

```bash
# Backend tests (if added)
pytest

# iOS tests
# Run in Xcode: Product → Test
```

### Debugging

For local development, use your Mac's IP address as the backend URL:

```swift
// In APIManager.swift
private let baseURL = "http://192.168.1.XXX:8000"
```

Ensure both devices are on the same network.

## License

MIT License - feel free to use this project for learning or building your own apps.

## Contributing

Contributions welcome! Areas for improvement:
- Share Sheet extension
- Additional AI providers (OpenAI, Anthropic)
- UI/UX refinements
- Accessibility improvements

---

Built with ❤️ for faster texting
