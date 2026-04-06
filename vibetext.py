#!/usr/bin/env python3
"""
VibeText CLI - 100% Local AI-powered text response generator.
Uses Ollama to ensure your messages never leave your computer.
"""

import os
import sys
import json
import argparse
import subprocess
import httpx
from typing import Optional, List

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Tone definitions
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
                return f"Error: Ollama returned {response.status_code}. Make sure model '{model}' is installed (run 'ollama pull {model}')."
    except Exception as e:
        return f"Error connecting to Ollama: {str(e)}\nEnsure Ollama is running (https://ollama.com)."

def build_prompt(original: str, draft: Optional[str], tone_info: tuple, vibe_profile: Optional[str] = None) -> str:
    """Constructs the prompt (matching backend logic)."""
    name, _, instruction = tone_info
    
    system_setup = "You are an AI assistant helping someone respond to a text message."
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
    parser = argparse.ArgumentParser(description="VibeText CLI - 100% Local AI Text Responder")
    parser.add_argument("--model", default="llama3", help="Ollama model to use (default: llama3)")
    parser.add_argument("--vibe", help="Path to your vibe profile (default: my_vibe_profile.txt if it exists)")
    args = parser.parse_args()

    print("\n--- VibeText CLI (Local Mode) ---")
    
    vibe_path = args.vibe or "my_vibe_profile.txt"
    vibe_content = None
    if os.path.exists(vibe_path):
        try:
            with open(vibe_path, "r", encoding="utf-8") as f:
                vibe_content = f.read().strip()
            print(f"✅ Loaded personal vibe profile from {vibe_path}")
        except Exception:
            pass
            
    # 1. Get Original Message
    clipboard = get_clipboard_text()
    if clipboard:
        print(f"Detected in clipboard: \"{clipboard[:50]}{'...' if len(clipboard)>50 else ''}\"")
        use_clip = input("Use clipboard text? (Y/n): ").lower() != 'n'
        original = clipboard if use_clip else input("Enter message: ")
    else:
        original = input("Enter message: ")

    if not original:
        return

    # 2. Get Optional Draft
    draft = input("\nYour draft/ideas (optional, press Enter to skip): ").strip()
    draft = draft if draft else None

    # 3. Choose Tone
    print("\nChoose Tone:")
    for key, (name, icon, _) in TONES.items():
        print(f"  {key}. {icon} {name}")
    
    tone_choice = input("\nSelect (1-5, default 1): ").strip() or "1"
    selected_tone = TONES.get(tone_choice, TONES["1"])

    # 4. Generate
    print(f"\nGenerating {selected_tone[0]} response using local Ollama ({args.model})...")
    
    prompt = build_prompt(original, draft, selected_tone, vibe_content)
    reply = call_ollama(prompt, args.model)

    # 5. Output
    print("\n" + "="*40)
    print(f"SUGGESTED REPLY:")
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
