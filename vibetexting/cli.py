import os
import sys
import argparse
import subprocess
import time
from .config import (
    load_user_config,
    save_user_config,
    merge_runtime_settings,
    DEFAULT_INTENT_MODE,
    INTENT_MODES,
)
from .database import (
    load_recent_chat_history,
    list_recent_group_chats,
    search_relevant_history,
    resolve_chat_matches,
    get_latest_message_date,
    get_latest_message_for_chat
)
from .prompts import (
    needs_manual_response,
    is_question_message,
    prompt_for_intent,
    prompt_for_intent_choice,
    prompt_for_barebones_answer,
    build_prompt,
)
from .llm import call_local_llm, list_ollama_models, list_lmstudio_models, start_lmstudio_server, stop_lmstudio_server
from .utils import get_clipboard_text, send_imessage
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML, ANSI

# ANSI color codes for prettier CLI
CLR_VIBE = "\033[1;35m"  # Bold Magenta
CLR_PRE = "\033[1;32m"   # Bold Green
CLR_USR = "\033[1;34m"   # Bold Blue
CLR_ERR = "\033[1;31m"   # Bold Red
CLR_DIM = "\033[2m"      # Dim
CLR_BOLD = "\033[1m"
CLR_RESET = "\033[0m"

def print_help():
    print(f"\n{CLR_VIBE}--- VibeText Interactive Help ---{CLR_RESET}")
    print(f"  {CLR_PRE}/chat [name]{CLR_RESET}   - Switch recipient and load history")
    print(f"  {CLR_PRE}/groups{CLR_RESET}       - List and switch to recent group chats")
    print(f"  {CLR_PRE}/model [name]{CLR_RESET}  - Switch to a specific model")
    print(f"  {CLR_PRE}/models{CLR_RESET}       - List all available local models")
    print(f"  {CLR_PRE}/limit [num]{CLR_RESET}   - Change message history limit")
    print(f"  {CLR_PRE}/delay [sec]{CLR_RESET}  - Set delay before auto-responding")
    print(f"  {CLR_PRE}/full{CLR_RESET}          - Use the WHOLE conversation as context")
    print(f"  {CLR_PRE}/goal [text]{CLR_RESET}   - Set a conversation goal (steers AI automatically)")
    print(f"  {CLR_PRE}/auto{CLR_RESET}           - Enter Auto-Pilot mode (monitors and replies automatically)")
    print(f"  {CLR_PRE}/vibe [path]{CLR_RESET}   - Switch vibe profile file")
    print(f"  {CLR_PRE}/paste{CLR_RESET}        - Use text from clipboard as message")
    print(f"  {CLR_PRE}/auto [mins]{CLR_RESET}   - Auto-reply mode (monitors for new messages)")
    print(f"  {CLR_PRE}/help{CLR_RESET}         - Show this menu")
    print(f"  {CLR_PRE}exit{CLR_RESET} or {CLR_PRE}quit{CLR_RESET}  - Exit VibeText")
    print(f"\nJust type your message and press Enter to generate a reply.")

def prompt_setup_config() -> dict:
    print(f"\n{CLR_VIBE}--- VibeText Setup ---{CLR_RESET}")
    print("This will save your default user profile for future runs. Press Enter to keep a value blank.")
    name = input("Your name [optional]: ").strip()
    vibe = input("Vibe profile path [default: my_vibe_profile.txt]: ").strip() or "my_vibe_profile.txt"
    backend = input("LLM backend [auto/ollama/lmstudio, default: auto]: ").strip().lower() or "auto"
    if backend not in {"auto", "ollama", "lmstudio"}:
        print(f"{CLR_ERR}Invalid backend. Using default: auto{CLR_RESET}")
        backend = "auto"
    default_model = "llama3" if backend in {"auto", "ollama"} else ""
    model_prompt = f"Model name [default: {default_model}]: " if default_model else "Model name (as shown in LM Studio): "
    model = input(model_prompt).strip() or default_model
    intent_mode = input("Intent mode [uncertain/suggest/always, default: uncertain]: ").strip().lower() or DEFAULT_INTENT_MODE
    if intent_mode not in INTENT_MODES:
        print(f"{CLR_ERR}Invalid intent mode. Using default: {DEFAULT_INTENT_MODE}{CLR_RESET}")
        intent_mode = DEFAULT_INTENT_MODE
    default_recipient = input("Default recipient key [optional, e.g. mom]: ").strip()
    recipients = {}
    if default_recipient:
        chat = input(f"Chat lookup for '{default_recipient}' [default: {default_recipient}]: ").strip() or default_recipient
        history_limit_raw = input("History limit for this recipient [blank = fallback]: ").strip()
        recipient_config = {"chat": chat}
        if history_limit_raw:
            try:
                recipient_config["history_limit"] = int(history_limit_raw)
            except ValueError:
                print(f"{CLR_ERR}Invalid number. Using fallback.{CLR_RESET}")
        recipients[default_recipient] = recipient_config
    config = {
        "name": name or None,
        "backend": backend,
        "model": model or None,
        "intent_mode": intent_mode,
        "vibe": vibe,
        "default_recipient": default_recipient or None,
        "recipients": recipients or None,
    }
    return {key: value for key, value in config.items() if value is not None}

def run_autopilot(args, config, chat_filter, vibe_content, goal, session=None):
    """Monitors chat history and automatically replies to new messages."""
    print(f"\n{CLR_VIBE}--- 🤖 Auto-Pilot Mode Active ---{CLR_RESET}")
    if not goal:
        print(f"{CLR_ERR}No goal set!{CLR_RESET}")
        if session:
            goal = session.prompt(ANSI(f"{CLR_USR}What is the goal for this autonomous conversation?{CLR_RESET} ")).strip()
        else:
            goal = input(f"{CLR_USR}What is the goal for this autonomous conversation?{CLR_RESET} ").strip()
        if not goal:
            print(f"{CLR_ERR}Goal required for Auto-Pilot. Returning to interactive mode.{CLR_RESET}")
            return goal

    print(f"{CLR_DIM}Monitoring conversations with '{chat_filter}'...{CLR_RESET}")
    print(f"{CLR_DIM}Active Goal: {CLR_RESET}{goal}")
    print(f"{CLR_DIM}Press Ctrl+C to stop.{CLR_RESET}\n")

    # Debug: Log initial state
    print(f"\n{CLR_DIM}[DEBUG] Auto-Pilot initialized with:{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   chat_filter: {chat_filter}{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   goal: {goal}{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   model: {args.model or 'llama3'}{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   backend: {args.backend or 'auto'}{CLR_RESET}\n")

    # Initialize last_history to None so the first poll iteration can process the current state
    # This allows it to "carry on the conversation" from the last existing message.
    _, initial_count, resolved_label, is_group_chat, chat_context, chat_id, chat_guid, last_is_from_me = load_recent_chat_history(chat_filter, 1, auto_select=True)
    last_history = None
    
    if not chat_id:
        print(f"{CLR_ERR}Could not resolve chat for Auto-Pilot monitoring.{CLR_RESET}")
        return goal

    print(f"{CLR_DIM}[DEBUG] Auto-Pilot Monitoring:{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   Recipient: {resolved_label} (ID: {chat_id}){CLR_RESET}")
    
    if initial_count == 0:
        print(f"{CLR_ERR}⚠️ No messages found in this chat. If you are on restricted WiFi, iMessage may not be syncing to this Mac.{CLR_RESET}")
        print(f"{CLR_DIM}Check if new messages are appearing in your macOS Messages app.{CLR_RESET}")
    else:
        status = f"Last message from {resolved_label}." if not last_is_from_me else "Last message from you."
        print(f"{CLR_PRE}✅ Ready. {status}{CLR_RESET}")
    print()

    iteration = 0
    try:
        while True:
            iteration += 1
            # Poll every 5 seconds
            if iteration > 1:
                time.sleep(5)
            
            # Use fixed chat_id for polling to avoid re-resolution issues
            current_history, current_count, _, _, _, _, _, current_is_from_me = load_recent_chat_history(resolved_label, 1, auto_select=True, chat_id=chat_id)

            # If this is the first poll or history has changed (either text or count)
            if (current_history, current_count) != last_history:
                if last_history is not None:
                    print(f"\n{CLR_VIBE}🔔 New activity detected! (Total: {current_count}){CLR_RESET}")
                
                # Get the actual last message content to see who sent it
                history_full, count, label, is_group, context, cid, cguid, is_from_me_latest = load_recent_chat_history(resolved_label, args.history_limit or 20, auto_select=True, chat_id=chat_id)

                lines = history_full.strip().split("\n")
                if not lines:
                    last_history = (current_history, current_count)
                    continue

                if is_from_me_latest:
                    # We sent this message. Skip replying but update last_history.
                    if last_history is not None:
                        print(f"{CLR_DIM}Last message is from you. Monitoring for a reply...{CLR_RESET}")
                    last_history = (current_history, current_count)
                    continue

                new_count = 1
                if last_history is not None:
                    new_count = current_count - last_history[1]
                
                # Make sure we don't try to extract more lines than we have
                new_count = max(1, min(new_count, len(lines)))
                new_lines = lines[-new_count:]

                # New incoming message detected (or starting from an incoming message)
                if new_count > 1:
                    print(f"\n{CLR_USR}Last {new_count} messages from {label}:{CLR_RESET}")
                else:
                    print(f"\n{CLR_USR}Last message from {label}:{CLR_RESET}")
                
                for line in new_lines:
                    print(f"{CLR_DIM}{line}{CLR_RESET}")

                # Extract the message text from the new lines (after the speaker label)
                # Format: [timestamp] Speaker: Text
                extracted_msgs = []
                for line in new_lines:
                    try:
                        extracted_msgs.append(line.split(": ", 1)[1])
                    except IndexError:
                        extracted_msgs.append(line)
                
                original_msg = " ".join(extracted_msgs)
                print(f"{CLR_DIM}[DEBUG] Extracted combined message: {original_msg}{CLR_RESET}")

                print(f"{CLR_DIM}[DEBUG] Searching for relevant memories...{CLR_RESET}")
                memories = search_relevant_history(chat_id, original_msg)
                print(f"{CLR_DIM}[DEBUG] Memories found: {memories is not None}{CLR_RESET}")

                delay_sec = getattr(args, 'delay', 0)
                if delay_sec > 0:
                    print(f"{CLR_DIM}Waiting {delay_sec} seconds before responding...{CLR_RESET}")
                    time.sleep(delay_sec)

                print(f"{CLR_DIM}Generating autonomous reply...{CLR_RESET}")
                
                print(f"{CLR_DIM}[DEBUG] Building prompt with:{CLR_RESET}")
                print(f"{CLR_DIM}[DEBUG]   original_msg: {original_msg[:50]}...{CLR_RESET}")
                print(f"{CLR_DIM}[DEBUG]   vibe_content: {vibe_content is not None}{CLR_RESET}")
                print(f"{CLR_DIM}[DEBUG]   history_full: {len(history_full) if history_full else 0} chars{CLR_RESET}")
                print(f"{CLR_DIM}[DEBUG]   label: {label}{CLR_RESET}")
                print(f"{CLR_DIM}[DEBUG]   context: {context is not None}{CLR_RESET}")
                print(f"{CLR_DIM}[DEBUG]   args.name: {args.name}{CLR_RESET}")
                print(f"{CLR_DIM}[DEBUG]   goal: {goal}{CLR_RESET}")
                
                prompt = build_prompt(
                    original_msg,
                    vibe_content,
                    history_full,
                    label,
                    context,
                    args.name,
                    None, # No user intent in auto mode
                    None, # No barebones answer
                    memories,
                    goal
                )

                print(f"{CLR_DIM}[DEBUG] Prompt length: {len(prompt)} chars{CLR_RESET}")
                print(f"{CLR_DIM}[DEBUG] Calling LLM with model: {args.model or 'llama3'}, backend: {args.backend or 'auto'}{CLR_RESET}")
                
                reply = call_local_llm(prompt, args.model or "llama3", args.backend or "auto")

                print(f"{CLR_DIM}[DEBUG] LLM response received, length: {len(reply)} chars{CLR_RESET}")
                
                if "Error" not in reply:
                    print(f"{CLR_PRE}🤖 Sending reply:{CLR_RESET} {reply}")
                    print(f"{CLR_DIM}[DEBUG] Sending to label: {label}, chat_guid: {cguid}{CLR_RESET}")
                    success = send_imessage(label, reply, chat_id=cguid)
                    if success:
                        print(f"{CLR_DIM}✅ Sent successfully.{CLR_RESET}")
                    else:
                        print(f"{CLR_ERR}❌ Failed to send via AppleScript.{CLR_RESET}")
                else:
                    print(f"{CLR_ERR}LLM Error: {reply}{CLR_RESET}")

                last_history = (current_history, current_count)
            else:
                pass
    except KeyboardInterrupt:
        print(f"\n{CLR_VIBE}--- Auto-Pilot Deactivated ---{CLR_RESET}")
        return goal

def main():
    parser = argparse.ArgumentParser(description="VibeText CLI - 100% Local AI Text Responder")
    parser.add_argument("--local", action="store_true", help="Compatibility flag for local mode (no-op)")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup to create your default config")
    parser.add_argument("--model", default=None, help="Model name to use")
    parser.add_argument("--backend", choices=["auto", "ollama", "lmstudio"], default=None, help="LLM backend to use")
    parser.add_argument("--name", help="Optional name for identity questions")
    parser.add_argument("--intent-mode", choices=sorted(INTENT_MODES), help="How to handle message intent")
    parser.add_argument("--vibe", help="Path to your vibe profile")
    parser.add_argument("--chat", help="Contact name or phone number")
    parser.add_argument("--history-limit", type=int, default=None, help="Max history messages")
    parser.add_argument("--delay", type=int, default=None, help="Delay in seconds before auto-responding")
    parser.add_argument("--full", action="store_true", help="Use the entire chat history as context (warning: may exceed model limit)")
    parser.add_argument("--list-groups", action="store_true", help="List recent group chats and exit")
    args = parser.parse_args()

    if args.setup:
        config = prompt_setup_config()
        config_path = save_user_config(config)
        print(f"\n{CLR_PRE}✅ Saved configuration to {config_path}{CLR_RESET}")
        return 0

    config = load_user_config()
    args = merge_runtime_settings(args, config)

    if args.list_groups:
        groups = list_recent_group_chats(limit=20)
        if not groups:
            print(f"{CLR_ERR}No recent group chats found.{CLR_RESET}")
            return 0
        print(f"\n{CLR_BOLD}Recent group chats:{CLR_RESET}")
        for idx, group in enumerate(groups, start=1):
            print(f"  {idx}. {group['label']} ({group['participant_count']} participants)")
        return 0

    print(f"\n{CLR_VIBE}--- VibeText CLI (Local Mode) ---{CLR_RESET}")
    if config.get("__path__"):
        print(f"{CLR_DIM}Loaded defaults from {config['__path__']}{CLR_RESET}")
    print(f"{CLR_DIM}Type {CLR_RESET}/help{CLR_DIM} to see available commands.{CLR_RESET}")

    # Auto-start Gemma/LM Studio server if needed
    backend = (getattr(args, "backend", None) or "auto").lower()
    model = (getattr(args, "model", None) or "llama3").lower()
    started_server = False
    if backend in {"auto", "lmstudio"} and "gemma" in model:
        print(f"{CLR_DIM}Checking for Gemma model server...{CLR_RESET}")
        if start_lmstudio_server():
            started_server = True
            print(f"{CLR_PRE}✅ Gemma server started automatically.{CLR_RESET}")
        else:
            print(f"{CLR_ERR}⚠️ Could not auto-start Gemma server. Please start LM Studio manually.{CLR_RESET}")

    chat_filter = args.chat
    first_run = True
    goal = None
    autopilot_active = False

    # Set up command completer for prompt-toolkit
    commands = [
        "/chat", "/groups", "/model", "/models", "/limit", "/delay", "/full",
        "/goal", "/auto", "/vibe", "/paste", "/help", "exit", "quit"
    ]
    completer = WordCompleter(commands, ignore_case=True)
    session = PromptSession(completer=completer)

    try:
        while True:
            # Skip vibe profile reload and user prompt during autopilot
            if not autopilot_active:
                vibe_path = args.vibe or "my_vibe_profile.txt"
                vibe_content = None
                if os.path.exists(vibe_path):
                    try:
                        with open(vibe_path, "r", encoding="utf-8") as f:
                            vibe_content = f.read().strip()
                        if first_run:
                            print(f"{CLR_PRE}✅ Loaded vibe profile: {vibe_path}{CLR_RESET}")
                    except Exception:
                        pass

                # Interactive Prompt
                print(f"{CLR_DIM}[DEBUG] About to prompt for user input (first_run={first_run}, args.chat={args.chat}){CLR_RESET}")
                if first_run and not args.chat:
                    clipboard = get_clipboard_text()
                    if clipboard:
                        print(f"\n{CLR_USR}Clipboard detected:{CLR_RESET} \"{clipboard[:60]}{'...' if len(clipboard)>60 else ''}\"")
                        choice = session.prompt(ANSI(f"Use this text? (Y/n/command): ")).strip().lower()
                        if choice == 'n':
                            original = session.prompt(ANSI(f"{CLR_PRE}vibetext{CLR_RESET}> ")).strip()
                        elif choice != '' and choice != 'y' and choice.startswith('/'):
                            original = choice
                        elif choice != '' and choice != 'y':
                            original = choice
                        else:
                            original = clipboard
                    else:
                        original = session.prompt(ANSI(f"{CLR_PRE}vibetext{CLR_RESET}> ")).strip()
                else:
                    prompt_label = f" ({chat_filter})" if chat_filter else ""
                    print(f"{CLR_DIM}[DEBUG] Prompting with label: {prompt_label}{CLR_RESET}")
                    original = session.prompt(ANSI(f"{CLR_PRE}vibetext{prompt_label}{CLR_RESET}> ")).strip()
                
                print(f"{CLR_DIM}[DEBUG] User input received: {original[:50]}...{CLR_RESET}")

                if not original:
                    first_run = False
                    continue

                # Command Handling
                cmd = original.lower()
                if cmd in ['exit', 'quit']:
                    print("Goodbye!")
                    break

                if cmd == '/help':
                    print_help()
                    first_run = False
                    continue

            if cmd.startswith('/goal'):
                parts = original.split(maxsplit=1)
                new_goal = parts[1] if len(parts) > 1 else ""
                if not new_goal:
                    new_goal = session.prompt(ANSI("\nEnter conversation goal (or 'clear' to remove): ")).strip()

                if new_goal.lower() == 'clear':
                    goal = None
                    print(f"{CLR_PRE}✅ Goal cleared.{CLR_RESET}")
                elif new_goal:
                    goal = new_goal
                    print(f"{CLR_PRE}✅ Goal set to: {goal}{CLR_RESET}")
                first_run = False
                continue

            if cmd == '/auto':
                print(f"\n{CLR_DIM}[DEBUG] /auto command triggered{CLR_RESET}")
                if not chat_filter:
                    print(f"{CLR_DIM}[DEBUG] No chat_filter set, prompting for recipient{CLR_RESET}")
                    chat_filter = session.prompt(ANSI(f"\n{CLR_USR}Who are you texting?{CLR_RESET} ")).strip() or None
                    print(f"{CLR_DIM}[DEBUG] User entered chat_filter: {chat_filter}{CLR_RESET}")
                else:
                    print(f"{CLR_DIM}[DEBUG] Using existing chat_filter: {chat_filter}{CLR_RESET}")

                if chat_filter:
                    print(f"{CLR_DIM}[DEBUG] Starting autopilot with chat_filter: {chat_filter}{CLR_RESET}")
                    autopilot_active = True
                    try:
                        goal = run_autopilot(args, config, chat_filter, vibe_content, goal, session=session)
                        print(f"{CLR_DIM}[DEBUG] Autopilot returned, goal: {goal}{CLR_RESET}")
                    finally:
                        autopilot_active = False
                else:
                    print(f"{CLR_ERR}A recipient must be set for Auto-Pilot.{CLR_RESET}")
                first_run = False
                continue

            if cmd == '/models':
                print(f"\n{CLR_DIM}Fetching available models...{CLR_RESET}")
                backend_type = (getattr(args, "backend", None) or "auto").lower()
                all_models = []
                if backend_type in {"auto", "ollama"}:
                    ollama_list = list_ollama_models()
                    if ollama_list:
                        print(f"{CLR_BOLD}Ollama:{CLR_RESET} {', '.join(ollama_list)}")
                        all_models.extend(ollama_list)
                if backend_type in {"auto", "lmstudio"}:
                    lm_list = list_lmstudio_models()
                    if lm_list:
                        print(f"{CLR_BOLD}LM Studio:{CLR_RESET} {', '.join(lm_list)}")
                        all_models.extend(lm_list)

                if not all_models:
                    print(f"{CLR_ERR}No models found. Check if backends are running.{CLR_RESET}")
                first_run = False
                continue

            if cmd.startswith('/model'):
                parts = original.split(maxsplit=1)
                new_model = parts[1] if len(parts) > 1 else ""
                if not new_model:
                    new_model = session.prompt(ANSI("\nEnter new model name: ")).strip()
                if new_model:
                    args.model = new_model
                    config['model'] = new_model
                    save_user_config(config)
                    print(f"{CLR_PRE}✅ Model set to '{new_model}'{CLR_RESET}")
                first_run = False
                continue

            if cmd.startswith('/limit'):
                parts = original.split(maxsplit=1)
                new_limit = parts[1] if len(parts) > 1 else ""
                if not new_limit:
                    new_limit = session.prompt(ANSI(f"Enter history limit (current: {args.history_limit}): ")).strip()
                if new_limit:
                    try:
                        limit_val = int(new_limit)
                        args.history_limit = limit_val
                        config['history_limit'] = limit_val
                        save_user_config(config)
                        print(f"{CLR_PRE}✅ History limit set to {limit_val}{CLR_RESET}")
                    except ValueError:
                        print(f"{CLR_ERR}Invalid number.{CLR_RESET}")
                first_run = False
                continue

            if cmd.startswith('/delay'):
                parts = original.split(maxsplit=1)
                new_delay = parts[1] if len(parts) > 1 else ""
                current_delay = getattr(args, 'delay', 0)
                if not new_delay:
                    new_delay = session.prompt(ANSI(f"Enter delay before auto-responding in seconds (current: {current_delay}): ")).strip()
                if new_delay:
                    try:
                        delay_val = int(new_delay)
                        args.delay = delay_val
                        config['delay'] = delay_val
                        save_user_config(config)
                        print(f"{CLR_PRE}✅ Auto-response delay set to {delay_val} seconds{CLR_RESET}")
                    except ValueError:
                        print(f"{CLR_ERR}Invalid number.{CLR_RESET}")
                first_run = False
                continue

            if cmd == '/full':
                args.history_limit = None
                config['history_limit'] = None
                save_user_config(config)
                print(f"{CLR_PRE}✅ Switched to FULL conversation history (no limit).{CLR_RESET}")
                print(f"{CLR_ERR}Warning: This may exceed your model's context window!{CLR_RESET}")
                first_run = False
                continue

            if cmd.startswith('/vibe'):
                parts = original.split(maxsplit=1)
                new_vibe = parts[1] if len(parts) > 1 else ""
                if not new_vibe:
                    new_vibe = session.prompt(ANSI("Enter vibe profile path: ")).strip()
                if new_vibe:
                    if os.path.exists(new_vibe):
                        args.vibe = new_vibe
                        config['vibe'] = new_vibe
                        save_user_config(config)
                        print(f"{CLR_PRE}✅ Vibe profile set to {new_vibe}{CLR_RESET}")
                    else:
                        print(f"{CLR_ERR}File not found: {new_vibe}{CLR_RESET}")
                first_run = False
                continue

            if cmd == '/paste':
                clip = get_clipboard_text()
                if clip:
                    original = clip
                    print(f"{CLR_USR}Pasted from clipboard.{CLR_RESET}")
                else:
                    print(f"{CLR_ERR}Clipboard is empty.{CLR_RESET}")
                    first_run = False
                    continue

            if cmd.startswith('/chat'):
                new_chat = original[5:].strip()
                if not new_chat:
                    chat_filter = session.prompt(ANSI("\nWho are you texting? ")).strip() or None
                else:
                    chat_filter = new_chat
                print(f"{CLR_PRE}✅ Recipient switched to '{chat_filter}'{CLR_RESET}")
                first_run = False
                continue

            if cmd == '/groups':
                groups = list_recent_group_chats(limit=10)
                if not groups:
                    print(f"{CLR_ERR}No recent group chats found.{CLR_RESET}")
                    continue
                print(f"\n{CLR_BOLD}Recent group chats:{CLR_RESET}")
                for idx, group in enumerate(groups, start=1):
                    print(f"  {idx}. {group['label']} ({group['participant_count']} participants)")
                selection = session.prompt(ANSI("Pick a number: ")).strip()
                if selection:
                    try:
                        selected_idx = int(selection)
                        if 1 <= selected_idx <= len(groups):
                            chat_filter = groups[selected_idx - 1]["label"]
                            print(f"{CLR_PRE}✅ Recipient switched to '{chat_filter}'{CLR_RESET}")
                        else:
                            print(f"{CLR_ERR}Invalid selection.{CLR_RESET}")
                    except ValueError:
                        print(f"{CLR_ERR}Invalid selection.{CLR_RESET}")
                first_run = False
                continue

            # If it's not a command, process as a message
            if not chat_filter:
                chat_filter = session.prompt(ANSI(f"\n{CLR_USR}Who are you texting?{CLR_RESET} (Enter to skip history): ")).strip() or None

            chat_history = None
            resolved_chat_label = None
            chat_context = None
            chat_id = None
            chat_guid = None
            if chat_filter:
                print(f"{CLR_DIM}Searching iMessage history for '{chat_filter}'...{CLR_RESET}")
                chat_history, message_count, resolved_chat_label, is_group_chat, chat_context, chat_id, chat_guid, last_is_from_me = load_recent_chat_history(chat_filter, args.history_limit)
                if chat_history:
                    label = resolved_chat_label or chat_filter
                    print(f"{CLR_PRE}✅ Loaded {message_count} messages from '{label}'{CLR_RESET}")
                else:
                    print(f"{CLR_DIM}No history found. Continuing without context.{CLR_RESET}")

            first_run = False

            # Search for relevant old memories based on keywords in the current message
            memories = None
            if chat_id and original and not original.startswith('/'):
                memories = search_relevant_history(chat_id, original)
                if memories:
                    print(f"{CLR_PRE}✅ Retrieved related memories from past conversations.{CLR_RESET}")

            user_intent = None
            user_barebones_answer = None

            # If a goal is set, skip manual intent prompting
            if goal:
                print(f"{CLR_DIM}Steering towards goal: {goal}{CLR_RESET}")
            else:
                if args.intent_mode == "always":
                    user_intent = prompt_for_intent_choice(original)
                elif args.intent_mode == "suggest":
                    if is_question_message(original):
                        user_barebones_answer = prompt_for_barebones_answer(original)
                    elif needs_manual_response(original):
                        user_intent = prompt_for_intent_choice(original)
                else:
                    if needs_manual_response(original):
                        user_intent = prompt_for_intent(original)

            backend = getattr(args, "backend", None) or "auto"
            model = getattr(args, "model", None) or "llama3"
            print(f"\n{CLR_DIM}Generating reply using {backend} ({model})...{CLR_RESET}")

            prompt = build_prompt(
                original,
                vibe_content,
                chat_history,
                resolved_chat_label or chat_filter,
                chat_context,
                args.name,
                user_intent,
                user_barebones_answer,
                memories,
                goal
            )
            reply = call_local_llm(prompt, model, backend)

            print(f"\n{CLR_VIBE}{'='*40}{CLR_RESET}")
            print(f"{CLR_BOLD}SUGGESTED REPLY:{CLR_RESET}")
            print(f"{CLR_DIM}{'-'*40}{CLR_RESET}")
            print(reply)
            print(f"{CLR_VIBE}{'='*40}{CLR_RESET}")

            if "Error" not in reply:
                try:
                    subprocess.run(['pbcopy'], input=reply, encoding='utf-8')
                    print(f"{CLR_DIM}(Copied to clipboard! 📋){CLR_RESET}")
                except Exception:
                    pass

            print()

    except KeyboardInterrupt:
        if not started_server:
            print(f"\n{CLR_PRE}✅ Server stopped.{CLR_RESET}")
    finally:
        # Stop the Gemma server if we started it
        if started_server:
            print(f"\n{CLR_DIM}Stopping Gemma server...{CLR_RESET}")
            stop_lmstudio_server()
            print(f"{CLR_PRE}✅ Server stopped.{CLR_RESET}")

if __name__ == "__main__":
    main()
