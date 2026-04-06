# VibeTexting iOS App

An iOS app that helps you respond to text messages faster using AI.

## Features

- 🎤 **Voice Input** - Dictate your reply using speech-to-text
- 🎨 **Tone Selection** - Choose from Casual, Professional, Funny, Friendly, or Concise
- 🤖 **AI-Powered** - Generates human-like responses via Groq API
- 📋 **Clipboard Detection** - Automatically detects messages from clipboard
- 🚀 **Fast & Native** - Built with SwiftUI for a smooth iOS experience

## Requirements

- iOS 16.0+
- Xcode 15.0+
- Backend server running (see `/backend` folder)

## Setup

### 1. Open in Xcode

```bash
cd iOS/VibeTexting
open VibeTexting.xcodeproj
```

### 2. Configure Backend URL

In `APIManager.swift`, update the `baseURL` to point to your backend server:

```swift
private let baseURL: String = "http://your-server:8000"
```

For local development, you can use your Mac's IP address.

### 3. Build and Run

Select your iOS device/simulator and press ⌘R to run.

## Project Structure

```
iOS/VibeTexting/
├── VibeTextingApp.swift    # App entry point
├── ContentView.swift        # Main UI screen
├── Models.swift             # Data models
├── APIManager.swift         # Backend API communication
├── VoiceInputManager.swift  # Speech recognition
├── ClipboardManager.swift   # Clipboard detection
└── Info.plist              # App configuration
```

## Usage

1. **Paste a message** from your clipboard or type it manually
2. **(Optional) Speak your reply** using the microphone button
3. **Select a tone** for your response
4. **Tap "Generate Reply"** to get AI-powered suggestions
5. **Copy or Share** the generated response

## Permissions

The app requires:
- **Speech Recognition** - For voice-to-text input

## UX Best Practices Implemented

- **1-2 taps** to get a reply after pasting a message
- **Visual feedback** during recording and generation
- **Clear tone indicators** with icons and descriptions
- **Error handling** with helpful messages
- **Large touch targets** for easy interaction

## Next Steps

- [ ] Add Share Sheet extension for direct messaging app integration
- [ ] Implement local storage for reply history
- [ ] Add favorite replies feature
- [ ] Support multiple languages
- [ ] Add custom tone presets
