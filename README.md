# VibeTexting 🎤

An iOS app that helps you respond to text messages faster using AI-powered tone-based response generation.

![iOS](https://img.shields.io/badge/iOS-16.0+-blue)
![Swift](https://img.shields.io/badge/Swift-5.9-orange)
![Platform](https://img.shields.io/badge/Platform-iOS-lightgrey)

## Features

- 🎤 **Voice Input** - Dictate your reply using iOS Speech framework
- 🎨 **5 Tone Options** - Casual, Professional, Funny, Friendly, Concise
- 🤖 **AI-Powered** - Fast responses via Groq API (Llama 3.1)
- 📋 **Clipboard Detection** - Auto-detect messages from clipboard
- 💾 **Local Storage** - History and favorites persistence
- 🚀 **Native UX** - SwiftUI with 1-2 tap response flow

## Project Structure

```
VibeTexting/
├── iOS/
│   └── VibeTexting/
│       ├── VibeTextingApp.swift    # App entry point
│       ├── ContentView.swift        # Main UI screen
│       ├── HistoryView.swift        # Reply history view
│       ├── Models.swift             # Data models
│       ├── APIManager.swift         # Backend API client
│       ├── VoiceInputManager.swift  # Speech recognition
│       ├── ClipboardManager.swift   # Clipboard monitoring
│       ├── StorageManager.swift     # Local persistence
│       └── Info.plist               # App config & permissions
├── backend/
│   ├── main.py                      # FastAPI server
│   ├── requirements.txt             # Python dependencies
│   └── .env                         # API keys (create this)
└── README.md                        # This file
```

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
