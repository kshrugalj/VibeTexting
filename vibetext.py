#!/usr/bin/env python3
"""
VibeText CLI - Local AI-powered text response generator.
Provides the same functionality as the VibeTexting iOS app directly in your terminal.
"""

import os
import sys
import json
import argparse
import subprocess
import httpx
from typing import Optional, List
from dotenv import load_dotenv

# Load environment variables (for Groq API key)
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Tone definitions (matching the iOS app)
TONES = {
    "1": ("Casual", "😎", "Keep it relaxed, friendly, and conversational."),
    "2": ("Professional", "💼", "Keep it polite, clear, and business-appropriate."),
    "3": ("Funny", "😄", "Add humor, wit, or a playful twist."),
    "4": ("Friendly", "🤗", "Warm, supportive, and kind."),
    "5": ("Concise", "⚡", "Brief and to the point. Minimal words.")
}

def get_clipboard_text() -> str:
    """Gets text from the system clipboard (macOS)."""
    try:
        return subprocess.check_output(['pbpaste'], encoding='utf-8').strip()
    except Exception:
        return ""

def call_groq(prompt: str) -> str:
    """Calls the Groq API for generation."""
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not found in backend/.env"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.7,
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(GROQ_API_URL, headers=headers, json=payload, timeout=20.0)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                return f"Error from Groq: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error calling Groq: {str(e)}"

def call_ollama(prompt: str, model: str = "llama3") -> str:
    """Calls a local Ollama instance for truly local generation."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(OLLAMA_API_URL, json=payload, timeout=60.0)
            if response.status_code == 200:
                return response.json()["response"].strip()
            else:
                return "Error: Ollama not running or model not found. Run 'ollama serve' and 'ollama pull llama3'."
    except Exception as e:
        return f"Error calling Ollama: {str(e)}\nMake sure Ollama is installed and running (https://ollama.com)."

def build_prompt(original: str, draft: Optional[str], tone_info: tuple, vibe_profile: Optional[str] = None) -> str:
    """Constructs the prompt (matching backend logic)."""
    name, _, instruction = tone_info
    
    system_setup = "You are helping someone respond to a text message."
    if vibe_profile:
        system_setup = f"You are an AI assistant that mimics my exact texting style.\n\nHere are some examples of how I text:\n{vibe_profile}\n\nWhen you reply, use the EXACT same vocabulary, capitalization style, phrasing, and punctuation habits as the examples above."
    
    if draft:
        return f"""{system_setup}

Original message: "{original}"
User's draft reply: "{draft}"
Tone: {name} - {instruction}

Refine the user's draft reply to match my style and the requested tone.
Keep it concise for a text message.
Response:"""
    else:
        return f"""{system_setup}

Original message: "{original}"
Tone: {name} - {instruction}

Generate a natural, human-like text response that matches my style and the requested tone.
Keep it concise and appropriate for a text message.
Response:"""

def main():
    parser = argparse.ArgumentParser(description="VibeText CLI - Local AI Text Responder")
    parser.add_argument("--local", action="store_true", help="Use local Ollama instead of Groq")
    parser.add_argument("--model", default="llama3", help="Ollama model to use (default: llama3)")
    parser.add_argument("--vibe", help="Path to your extracted vibe profile text file (e.g. my_vibe_profile.txt)")
    args = parser.parse_args()

    print("\n--- VibeText CLI ---")
    
    vibe_content = None
    if args.vibe:
        try:
            with open(args.vibe, "r", encoding="utf-8") as f:
                vibe_content = f.read().strip()
            print(f"✅ Loaded personal vibe profile ({len(vibe_content.splitlines())} examples)")
        except Exception as e:
            print(f"⚠️ Warning: Could not load vibe profile: {e}")
            
    # 1. Get Original Message
    clipboard = get_clipboard_text()
    if clipboard:
        print(f"Detected in clipboard: \"{clipboard[:50]}{'...' if len(clipboard)>50 else ''}\"")
        use_clip = input("Use clipboard text? (Y/n): ").lower() != 'n'
        original = clipboard if use_clip else input("Enter message to reply to: ")
    else:
        original = input("Enter message to reply to: ")

    if not original:
        print("Error: No message provided.")
        return

    # 2. Get Optional Draft
    draft = input("\nYour draft/ideas (optional, press Enter to skip): ").strip()
    draft = draft if draft else None

    # 3. Choose Tone
    print("\nChoose Tone:")
    for key, (name, icon, _) in TONES.items():
        print(f"  {key}. {icon} {name}")
    
    tone_choice = input("\nSelect (1-5, default 1): ").strip() or "1"
    if tone_choice not in TONES:
        print("Invalid choice, defaulting to Casual.")
        tone_choice = "1"
    
    selected_tone = TONES[tone_choice]

    # 4. Generate
    print(f"\nGenerating {selected_tone[0]} response using {'Ollama (' + args.model + ')' if args.local else 'Groq'}...")
    
    prompt = build_prompt(original, draft, selected_tone, vibe_content)
    
    if args.local:
        reply = call_ollama(prompt, args.model)
    else:
        reply = call_groq(prompt)

    # 5. Output
    print("\n" + "="*40)
    print(f"SUGGESTED REPLY ({selected_tone[0]}):")
    print("-" * 40)
    print(reply)
    print("="*40)
    
    if "Error" not in reply:
        try:
            subprocess.run(['pbcopy'], input=reply, encoding='utf-8')
            print("\n(Copied to clipboard! 📋)")
        except Exception:
            pass
    print()

if __name__ == "__main__":
    main()
