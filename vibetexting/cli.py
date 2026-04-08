import os
import sys
import argparse
import subprocess
from .config import (
    load_user_config,
    save_user_config,
    merge_runtime_settings,
    DEFAULT_INTENT_MODE,
    INTENT_MODES,
)
from .database import load_recent_chat_history
from .prompts import (
    needs_manual_response,
    prompt_for_intent,
    prompt_for_intent_choice,
    build_prompt,
)
from .llm import call_ollama
from .utils import get_clipboard_text # I'll add this to utils.py next

def prompt_setup_config() -> dict:
    print("\n--- VibeText Setup ---")
    print("This will save your default user profile for future runs. Press Enter to keep a value blank.")
    name = input("Your name [optional]: ").strip()
    vibe = input("Vibe profile path [default: my_vibe_profile.txt]: ").strip() or "my_vibe_profile.txt"
    model = input("Ollama model [default: llama3]: ").strip() or "llama3"
    intent_mode = input("Intent mode [uncertain/suggest/always, default: uncertain]: ").strip().lower() or DEFAULT_INTENT_MODE
    if intent_mode not in INTENT_MODES:
        print(f"Invalid intent mode. Using default: {DEFAULT_INTENT_MODE}")
        intent_mode = DEFAULT_INTENT_MODE
    default_recipient = input("Default recipient key [optional, e.g. mom]: ").strip()
    recipients = {}
    if default_recipient:
        chat = input(f"Chat lookup for '{default_recipient}' [default: {default_recipient}]: ").strip() or default_recipient
        history_limit_raw = input("History limit for this recipient [blank = full conversation]: ").strip()
        recipient_config = {"chat": chat}
        if history_limit_raw:
            try:
                recipient_config["history_limit"] = int(history_limit_raw)
            except ValueError:
                print("Invalid number provided. Using full conversation for this recipient.")
        recipients[default_recipient] = recipient_config
    config = {
        "name": name or None,
        "model": model,
        "intent_mode": intent_mode,
        "vibe": vibe,
        "default_recipient": default_recipient or None,
        "recipients": recipients or None,
    }
    return {key: value for key, value in config.items() if value is not None}

def main():
    parser = argparse.ArgumentParser(description="VibeText CLI - 100% Local AI Text Responder")
    parser.add_argument("--local", action="store_true", help="Compatibility flag for local mode (no-op)")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup to create your default config")
    parser.add_argument("--model", default="llama3", help="Ollama model to use (default: llama3)")
    parser.add_argument("--name", help="Optional name to use for direct identity questions")
    parser.add_argument("--intent-mode", choices=sorted(INTENT_MODES), help="How to handle messages that need your real intent")
    parser.add_argument("--vibe", help="Path to your vibe profile (default: my_vibe_profile.txt if it exists)")
    parser.add_argument("--chat", help="Contact name, phone number, or email to load recent chat history")
    parser.add_argument("--history-limit", type=int, default=None, help="Max messages to include from that chat (default: full conversation)")
    parser.add_argument("--loop", "-l", action="store_true", help="Keep the program running for multiple messages")
    args = parser.parse_args()

    if args.setup:
        config = prompt_setup_config()
        config_path = save_user_config(config)
        print(f"\n✅ Saved configuration to {config_path}")
        return 0

    config = load_user_config()
    args = merge_runtime_settings(args, config)
    print("\n--- VibeText CLI (Local Mode) ---")
    if config.get("__path__"):
        print(f"✅ Loaded user defaults from {config['__path__']}")
    
    vibe_path = args.vibe or "my_vibe_profile.txt"
    vibe_content = None
    if os.path.exists(vibe_path):
        try:
            with open(vibe_path, "r", encoding="utf-8") as f:
                vibe_content = f.read().strip()
            print(f"✅ Loaded personal vibe profile from {vibe_path}")
        except Exception:
            pass

    chat_filter = args.chat
    first_run = True
    while True:
        if first_run:
            clipboard = get_clipboard_text()
            if clipboard:
                print(f"Detected in clipboard: \"{clipboard[:50]}{'...' if len(clipboard)>50 else ''}\"")
                use_clip = input("Use clipboard text? (Y/n): ").lower() != 'n'
                original = clipboard if use_clip else input("Enter message: ")
            else:
                original = input("Enter message: ")
        else:
            print("\n" + "-"*40)
            original = input("Enter message (or 'exit' to quit, '/chat' to switch): ").strip()

        if original.lower() in ['exit', 'quit']:
            if not first_run:
                print("Goodbye!")
            break
        if not original:
            if not args.loop:
                break
            continue
        if original.startswith('/chat'):
            new_chat = original[5:].strip()
            if not new_chat:
                chat_filter = input("\nWho are you texting? (name, number, or Enter to skip history): ").strip() or None
            else:
                chat_filter = new_chat
            print(f"✅ Switched recipient to '{chat_filter or 'None'}'")
            continue

        if not chat_filter:
            chat_filter = input("\nWho are you texting? (name, number, or Enter to skip history): ").strip() or None

        chat_history = None
        resolved_chat_label = None
        if chat_filter:
            print(f"Searching recent chat history for '{chat_filter}'...")
            chat_history, message_count, resolved_chat_label = load_recent_chat_history(chat_filter, args.history_limit)
            if chat_history:
                label = resolved_chat_label or chat_filter
                if args.history_limit is None:
                    print(f"✅ Loaded the full conversation with '{label}' ({message_count} messages)")
                else:
                    print(f"✅ Loaded {message_count} messages from '{label}'")
            else:
                print("No matching chat history found. Continuing without chat context.")

        first_run = False
        user_intent = None
        if args.intent_mode == "always":
            user_intent = prompt_for_intent_choice(original)
        elif args.intent_mode == "suggest":
            if needs_manual_response(original):
                user_intent = prompt_for_intent_choice(original)
        else:
            if needs_manual_response(original):
                user_intent = prompt_for_intent(original)

        print(f"\nGenerating a reply using your sent-message style with local Ollama ({args.model})...")
        prompt = build_prompt(original, vibe_content, chat_history, resolved_chat_label or chat_filter, args.name, user_intent)
        reply = call_ollama(prompt, args.model)
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
        if not args.loop:
            break
        print()

if __name__ == "__main__":
    main()
