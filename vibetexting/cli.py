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
    resolve_chat_matches,
    get_latest_message_date,
    get_latest_message_for_chat
)
from .providers.imessage import IMessageProvider
from .prompts import (
    needs_manual_response,
    is_question_message,
    prompt_for_intent,
    prompt_for_intent_choice,
    prompt_for_barebones_answer,
    build_prompt,
)
from .llm import call_local_llm, list_ollama_models, list_lmstudio_models, start_lmstudio_server, stop_lmstudio_server
from .evals import score_vibe_match, print_vibe_score
from .feedback import maybe_ask_feedback, load_feedback_notes
from .utils import get_clipboard_text
from .wrapped import get_global_wrapped
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
    print(f"  {CLR_PRE}/wrapped [flags]{CLR_RESET} - Your Wrapped — global stats about you (default: 2026)")
    print(f"  {CLR_PRE}/paste{CLR_RESET}        - Use text from clipboard as message")
    print(f"  {CLR_PRE}/help{CLR_RESET}         - Show this menu")
    print(f"  {CLR_PRE}exit{CLR_RESET} or {CLR_PRE}quit{CLR_RESET}  - Exit VibeText")
    print(f"\nJust type your message and press Enter to generate a reply.")
    print(f"{CLR_DIM}Tip: /wrapped --help for all Wrapped options (year, range, all-time).{CLR_RESET}")


def print_wrapped_help():
    print(f"\n{CLR_VIBE}--- Wrapped Help (/wrapped) ---{CLR_RESET}")
    print(f"  {CLR_BOLD}Your Wrapped — fun, shareable story about your texting. 100% local.{CLR_RESET}")
    print(f"\n  {CLR_PRE}Usage:{CLR_RESET}")
    print(f"    /wrapped                    -> 2026 (default)")
    print(f"    /wrapped --year 2024        -> single year")
    print(f"    /wrapped --year all         -> all time since your first text")
    print(f"    /wrapped --all              -> same as --year all")
    print(f"    /wrapped --from 2022 --to 2024  -> range inclusive")
    print(f"    /wrapped --range 2022-2024  -> same as above")
    print(f"    /wrapped --from 2022        -> 2022 to now")
    print(f"    /wrapped --to 2023          -> beginning to 2023")
    print(f"    /wrapped 2024               -> shorthand for --year 2024")
    print(f"\n  {CLR_PRE}Flags:{CLR_RESET}")
    print(f"    --year YYYY | all           single year or all-time")
    print(f"    --from YYYY                 start year (inclusive)")
    print(f"    --to YYYY                   end year (inclusive)")
    print(f"    --range YYYY-YYYY           start-end shorthand")
    print(f"    --all                       all-time alias")
    print(f"    --cache                     enable caching (saves to ~/.vibetexting/wrapped_cache/)")
    print(f"    --no-cache                  disable caching (default)")
    print(f"    --help, -h                  show this help")
    print(f"\n  {CLR_PRE}Examples:{CLR_RESET}")
    print(f"    /wrapped")
    print(f"    /wrapped --year 2024 --cache")
    print(f"    /wrapped --range 2022-2024 --cache")
    print(f"    /wrapped --year all --no-cache")
    print(f"\n  {CLR_DIM}Cache is optional and off by default. Add --cache to save/load from wrapped_cache for faster repeat runs.{CLR_RESET}")
    print(f"\n  Cards: Volume • Circle • Prime Time • Signature • Streaks • Loyal One • Day One")


def _parse_wrapped_args(arg_str: str):
    """
    Parse /wrapped flags.
    Returns (year_from, year_to, use_cache, show_help, error_msg)
    year_from/year_to are ints or None. Both None = all-time.
    Default if no args: 2026, 2026, no cache.
    """
    args = arg_str.strip().split() if arg_str.strip() else []
    if not args:
        return 2026, 2026, False, False, None
    # help check
    if any(a in ("--help", "-h") for a in args):
        return None, None, False, True, None
    year = None
    year_from = None
    year_to = None
    use_all = False
    use_cache = False
    # Track explicit cache flags; default off
    cache_tok_seen = False
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--year" and i + 1 < len(args):
            val = args[i + 1]
            if val.lower() == "all":
                use_all = True
            else:
                try:
                    year = int(val)
                except ValueError:
                    return None, None, False, False, f"Invalid year '{val}'"
            i += 2
        elif tok == "--all":
            use_all = True
            i += 1
        elif tok == "--cache":
            use_cache = True
            cache_tok_seen = True
            i += 1
        elif tok == "--no-cache":
            use_cache = False
            cache_tok_seen = True
            i += 1
        elif tok == "--from" and i + 1 < len(args):
            try:
                year_from = int(args[i + 1])
            except ValueError:
                return None, None, False, False, f"Invalid --from year '{args[i+1]}'"
            i += 2
        elif tok == "--to" and i + 1 < len(args):
            try:
                year_to = int(args[i + 1])
            except ValueError:
                return None, None, False, False, f"Invalid --to year '{args[i+1]}'"
            i += 2
        elif tok == "--range" and i + 1 < len(args):
            val = args[i + 1]
            if "-" not in val:
                return None, None, False, False, f"Invalid --range '{val}' (expected YYYY-YYYY)"
            a, b = val.split("-", 1)
            try:
                year_from = int(a.strip())
                year_to = int(b.strip())
            except ValueError:
                return None, None, False, False, f"Invalid --range '{val}'"
            i += 2
        elif tok.startswith("--"):
            return None, None, False, False, f"Unknown flag '{tok}'"
        else:
            # positional: year or all
            if tok.lower() == "all":
                use_all = True
            else:
                try:
                    year = int(tok)
                except ValueError:
                    return None, None, False, False, f"Unknown argument '{tok}'"
            i += 1
    if use_all:
        return None, None, use_cache, False, None
    if year is not None:
        if year_from is not None or year_to is not None:
            return None, None, False, False, "Don't combine --year with --from/--to/--range"
        return year, year, use_cache, False, None
    if year_from is not None or year_to is not None:
        if year_from is not None and year_to is not None and year_from > year_to:
            return None, None, False, False, f"--from {year_from} is after --to {year_to}"
        return year_from, year_to, use_cache, False, None
    # fallback (shouldn't reach due to empty check)
    return 2026, 2026, use_cache, False, None


def _print_wrapped_story(data: dict, session=None):
    if data.get("error"):
        print(f"{CLR_ERR}Wrapped error: {data['error']}{CLR_RESET}")
        return
    range_label = data.get("range_label", "2026")
    volume = data.get("volume", {})
    circle = data.get("circle", {})
    prime = data.get("prime_time", {})
    sig = data.get("signature", {})
    streaks = data.get("streaks", {})
    loyal = data.get("loyal_one", {})
    day_one = data.get("day_one", {})

    def _pause():
        try:
            if session:
                session.prompt(ANSI(f"{CLR_DIM}Press Enter for next card…{CLR_RESET} "))
            else:
                input(f"{CLR_DIM}Press Enter for next card…{CLR_RESET} ")
        except (KeyboardInterrupt, EOFError):
            print()
            raise KeyboardInterrupt

    total_in_range = circle.get("total_messages_in_range", volume.get("total_in_range", 0))
    # Header
    print(f"\n{CLR_VIBE}{'═'*52}{CLR_RESET}")
    print(f"{CLR_BOLD}  🎁  YOUR WRAPPED — {range_label}  🎁{CLR_RESET}")
    print(f"{CLR_DIM}  {data.get('generated_at','')} • 100% local • {total_in_range} msgs in range{CLR_RESET}")
    print(f"{CLR_VIBE}{'═'*52}{CLR_RESET}")

    # Card 1: Volume
    print(f"\n{CLR_BOLD}[1/7]  YOUR VOLUME{CLR_RESET}")
    print(f"{CLR_DIM}{'─'*52}{CLR_RESET}")
    sent = volume.get("sent", 0)
    if sent == 0 and total_in_range == 0:
        print(f"  No messages in this range.")
    else:
        print(f"  {CLR_PRE}{sent:,}{CLR_RESET} texts sent by you")
        print(f"  {CLR_DIM}{total_in_range:,} total messages in this period (you + them){CLR_RESET}")
        if sent > 0:
            print(f"  {CLR_DIM}That's about {sent//365 if sent>365 else sent} per day on average{CLR_RESET}")
    try:
        _pause()
    except KeyboardInterrupt:
        return

    # Card 2: Circle
    print(f"\n{CLR_BOLD}[2/7]  YOUR CIRCLE{CLR_RESET}")
    print(f"{CLR_DIM}{'─'*52}{CLR_RESET}")
    distinct = circle.get("distinct_chats_you_texted", 0)
    top = circle.get("top_chats", [])
    print(f"  {CLR_PRE}{distinct}{CLR_RESET} people you texted")
    if top:
        print(f"  {CLR_DIM}Top conversations by volume:{CLR_RESET}")
        for idx, ch in enumerate(top, 1):
            print(f"    {idx}. {CLR_BOLD}{ch['label']}{CLR_RESET} — {ch['count']:,} msgs")
    else:
        print(f"  {CLR_DIM}No conversations found in this range{CLR_RESET}")
    try:
        _pause()
    except KeyboardInterrupt:
        return

    # Card 3: Prime Time
    print(f"\n{CLR_BOLD}[3/7]  YOUR PRIME TIME{CLR_RESET}")
    print(f"{CLR_DIM}{'─'*52}{CLR_RESET}")
    peak_h = prime.get("peak_hour_label")
    peak_h_cnt = prime.get("peak_hour_count", 0)
    peak_wd = prime.get("peak_weekday")
    late = sig.get("late_night_count", 0)
    if peak_h:
        print(f"  Peak hour: {CLR_PRE}{peak_h}{CLR_RESET} ({peak_h_cnt} msgs)")
        print(f"  Peak day:  {CLR_PRE}{peak_wd}{CLR_RESET} ({prime.get('peak_weekday_count',0)} msgs)")
        # tiny histogram top 3 hours
        hist = prime.get("hour_histogram", {})
        if hist:
            top_hours = sorted(hist.items(), key=lambda x: x[1], reverse=True)[:3]
            # format
            def _fh(h):
                suf = "am" if int(h) < 12 else "pm"
                hr = int(h) % 12 or 12
                return f"{hr}{suf}"
            print(f"  {CLR_DIM}Top hours: {', '.join(f'{_fh(h)}:{c}' for h,c in top_hours)}{CLR_RESET}")
        print(f"  {CLR_DIM}Late night (12-4am): {late} texts{CLR_RESET}")
    else:
        print(f"  {CLR_DIM}No timing data{CLR_RESET}")
    try:
        _pause()
    except KeyboardInterrupt:
        return

    # Card 4: Signature
    print(f"\n{CLR_BOLD}[4/7]  YOUR SIGNATURE{CLR_RESET}")
    print(f"{CLR_DIM}{'─'*52}{CLR_RESET}")
    avg = sig.get("avg_words", 0)
    med = sig.get("median_words", 0)
    lower = sig.get("lowercase_pct", 0)
    emojis = sig.get("top_emojis", [])
    epm = sig.get("emoji_per_msg", 0)
    print(f"  Avg length: {CLR_PRE}{avg} words/msg{CLR_RESET} (median {med})")
    print(f"  Lowercase style: {CLR_PRE}{lower}%{CLR_RESET} of your msgs")
    if emojis:
        emo_str = "  ".join(f"{e['emoji']}×{e['count']}" for e in emojis[:3])
        print(f"  Signature emojis: {emo_str}  {CLR_DIM}({epm} per msg){CLR_RESET}")
    else:
        print(f"  {CLR_DIM}No emoji — you're pure text{CLR_RESET}")
    try:
        _pause()
    except KeyboardInterrupt:
        return

    # Card 5: Streaks (two-way)
    print(f"\n{CLR_BOLD}[5/7]  STREAKS (two-way days){CLR_RESET}")
    print(f"{CLR_DIM}{'─'*52}{CLR_RESET}")
    print(f"  {CLR_DIM}Counts only days where BOTH of you texted{CLR_RESET}")
    longest = streaks.get("longest", 0)
    longest_label = streaks.get("longest_chat_label")
    l_start = streaks.get("longest_start")
    l_end = streaks.get("longest_end")
    cur = streaks.get("current", 0)
    cur_label = streaks.get("current_chat_label")
    if longest and longest > 1:
        print(f"  Longest: {CLR_PRE}{longest} days{CLR_RESET} with {CLR_BOLD}{longest_label}{CLR_RESET}")
        print(f"           {CLR_DIM}{l_start} → {l_end}{CLR_RESET}")
    elif longest == 1:
        print(f"  Longest: 1 day with {longest_label} {CLR_DIM}(no multi-day streak yet){CLR_RESET}")
    else:
        print(f"  {CLR_DIM}No two-way streaks in this range{CLR_RESET}")
    if cur and cur > 0:
        print(f"  Current: {CLR_PRE}{cur} days{CLR_RESET} with {cur_label} {CLR_DIM}(ending today){CLR_RESET}")
    else:
        print(f"  {CLR_DIM}No active streak today{CLR_RESET}")
    try:
        _pause()
    except KeyboardInterrupt:
        return

    # Card 6: Loyal One
    print(f"\n{CLR_BOLD}[6/7]  YOUR LOYAL ONE{CLR_RESET}")
    print(f"{CLR_DIM}{'─'*52}{CLR_RESET}")
    print(f"  {CLR_DIM}Ranked by days you BOTH talked{CLR_RESET}")
    top3 = loyal.get("top3", [])
    if top3:
        for idx, entry in enumerate(top3, 1):
            marker = "→ " if idx == 1 else "  "
            print(f"  {marker}{idx}. {CLR_BOLD}{entry['label']}{CLR_RESET} — {entry['days']} two-way days")
        runner = loyal.get("runner_up")
        if runner:
            print(f"  {CLR_DIM}Runner-up was close!{CLR_RESET}")
    else:
        print(f"  {CLR_DIM}No two-way days in this range{CLR_RESET}")
    try:
        _pause()
    except KeyboardInterrupt:
        return

    # Card 7: Day One Flex
    print(f"\n{CLR_BOLD}[7/7]  DAY ONE FLEX{CLR_RESET}")
    print(f"{CLR_DIM}{'─'*52}{CLR_RESET}")
    first_date = day_one.get("first_message_date")
    first_text = day_one.get("first_message_text")
    days_since = day_one.get("days_since")
    if first_date:
        print(f"  First text in range: {CLR_PRE}{first_date}{CLR_RESET}")
        print(f"  {CLR_DIM}“{first_text}”{CLR_RESET}")
        if days_since is not None:
            print(f"  {CLR_DIM}{days_since} days ago{CLR_RESET}")
        print(f"  {CLR_DIM}Range: {range_label}{CLR_RESET}")
    else:
        print(f"  {CLR_DIM}No messages in this range to show first text{CLR_RESET}")

    print(f"\n{CLR_VIBE}{'═'*52}{CLR_RESET}")
    print(f"{CLR_BOLD}  That's your Wrapped — {range_label}!{CLR_RESET} {CLR_DIM}Run /wrapped --help for other years/ranges{CLR_RESET}")
    print(f"{CLR_VIBE}{'═'*52}{CLR_RESET}\n")

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

def run_autopilot(args, config, chat_filter, vibe_content, goal, provider, session=None, pinned_chat_id=None):
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

    last_history, last_count, resolved_label, is_group_chat, chat_context, chat_id, chat_guid, _ = provider.load_history(chat_filter, limit=1, auto_select=True, chat_id=pinned_chat_id)
    
    # Debug: Log initial history load
    print(f"{CLR_DIM}[DEBUG] Initial history loaded:{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   last_count: {last_count}{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   resolved_label: {resolved_label}{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   is_group_chat: {is_group_chat}{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   chat_id: {chat_id}{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   chat_guid: {chat_guid}{CLR_RESET}")
    print(f"{CLR_DIM}[DEBUG]   history length: {len(last_history) if last_history else 0} chars{CLR_RESET}\n")

    iteration = 0
    try:
        while True:
            iteration += 1
            print(f"\n{CLR_DIM}[DEBUG] === Polling iteration #{iteration} ==={CLR_RESET}")
            time.sleep(5) # Poll every 5 seconds
            
            print(f"{CLR_DIM}[DEBUG] Loading current history with filter: '{chat_filter}'{CLR_RESET}")
            current_history, current_count, _, _, _, _, current_chat_guid, _ = provider.load_history(chat_filter, limit=1, auto_select=True, chat_id=pinned_chat_id)
            print(f"{CLR_DIM}[DEBUG] Current history length: {len(current_history) if current_history else 0} chars, count: {current_count}{CLR_RESET}")

            # If the last message in history has changed and it's not from us
            if current_history != last_history:
                print(f"{CLR_DIM}[DEBUG] History changed! Old length: {len(last_history) if last_history else 0}, New length: {len(current_history) if current_history else 0}{CLR_RESET}")
                
                # Get the actual last message content to see who sent it
                # We reload with a small limit to inspect the latest
                history_full, count, label, is_group, context, cid, cguid, _ = provider.load_history(chat_filter, limit=args.history_limit or 20, auto_select=True, chat_id=pinned_chat_id)

                # Debug: Log the full history
                print(f"{CLR_DIM}[DEBUG] Reloaded history_full length: {len(history_full) if history_full else 0} chars{CLR_RESET}")
                
                # Check if the very last line starts with "Me:"
                lines = history_full.strip().split("\n")
                if not lines:
                    print(f"{CLR_DIM}[DEBUG] No lines in history, skipping{CLR_RESET}")
                    continue

                new_count = 1
                if last_history is not None:
                    new_count = current_count - last_count
                
                # Make sure we don't try to extract more lines than we have
                new_count = max(1, min(new_count, len(lines)))
                new_lines = lines[-new_count:]

                last_line = lines[-1]
                print(f"{CLR_DIM}[DEBUG] Last line: {last_line}{CLR_RESET}")
                
                if "]: Me: " in last_line:
                    # We sent this message, or at least the last message is ours. Skip.
                    print(f"{CLR_DIM}[DEBUG] Last message is from us, skipping{CLR_RESET}")
                    last_history = current_history
                    last_count = current_count
                    continue

                # New incoming message detected!
                if new_count > 1:
                    print(f"\n{CLR_USR}New messages detected ({new_count}):{CLR_RESET}")
                else:
                    print(f"\n{CLR_USR}New message detected:{CLR_RESET}")
                
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

                # --- V2.0: Dynamic Vibe Switching ---
                # Check if this specific recipient has a custom vibe profile
                active_vibe_content = vibe_content
                if config.get("recipients") and label in config["recipients"]:
                    recipient_vibe_path = config["recipients"][label].get("vibe")
                    if recipient_vibe_path and os.path.exists(recipient_vibe_path):
                        try:
                            with open(recipient_vibe_path, "r", encoding="utf-8") as f:
                                active_vibe_content = f.read().strip()
                                print(f"{CLR_DIM}[V2.0] Switched to custom vibe for {label}{CLR_RESET}")
                        except Exception:
                            pass

                print(f"{CLR_DIM}[DEBUG] Searching for relevant memories...{CLR_RESET}")
                memories = provider.search_memories(chat_id, original_msg)
                print(f"{CLR_DIM}[DEBUG] Memories found: {bool(memories)}{CLR_RESET}")

                print(f"{CLR_DIM}Generating autonomous reply...{CLR_RESET}")
                
                feedback_notes = load_feedback_notes()
                prompt = build_prompt(
                    original_msg,
                    active_vibe_content,
                    history_full,
                    label,
                    context,
                    args.name,
                    None, # No user intent in auto mode
                    None, # No barebones answer
                    memories,
                    goal,
                    feedback_notes,
                )

                reply = call_local_llm(prompt, args.model or "llama3", args.backend or "auto")
                
                if "Error" not in reply:
                    # --- V2.0: Natural Typing Delay ---
                    base_delay = getattr(args, 'delay', 0)
                    # Average human types at ~40-60 WPM. Let's assume ~12 chars per second.
                    typing_speed_factor = 0.08 # seconds per character
                    typing_delay = len(reply) * typing_speed_factor
                    total_delay = base_delay + typing_delay
                    
                    print(f"{CLR_DIM}🤖 Thinking finished. Simulating typing for {total_delay:.1f}s...{CLR_RESET}")
                    time.sleep(total_delay)

                    print(f"{CLR_PRE}🤖 Sending reply:{CLR_RESET} {reply}")

                    # --- Vibe Match Eval ---
                    if active_vibe_content:
                        try:
                            vibe_score = score_vibe_match(reply, active_vibe_content)
                            print_vibe_score(vibe_score)
                        except Exception:
                            pass

                    success = provider.send_message(label, reply, chat_id=cguid)
                    if success:
                        print(f"{CLR_DIM}✅ Sent successfully.{CLR_RESET}")
                    else:
                        print(f"{CLR_ERR}❌ Failed to send via AppleScript.{CLR_RESET}")
                else:
                    print(f"{CLR_ERR}LLM Error: {reply}{CLR_RESET}")

                last_history = current_history
                last_count = current_count
            else:
                print(f"{CLR_DIM}[DEBUG] No history change, continuing...{CLR_RESET}")
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
    parser.add_argument("--dashboard", action="store_true", help="Launch the local Ghost Dashboard (Web UI)")
    parser.add_argument("--wrapped", action="store_true", help="Show your Wrapped (global stats) and exit — default 2026. See /wrapped --help for flags")
    parser.add_argument("--year", default=None, help="Year for --wrapped (YYYY or 'all')")
    parser.add_argument("--from", dest="from_year", default=None, help="Start year for --wrapped range")
    parser.add_argument("--to", dest="to_year", default=None, help="End year for --wrapped range")
    parser.add_argument("--range", dest="range_year", default=None, help="Range for --wrapped (YYYY-YYYY)")
    parser.add_argument("--all", dest="all_flag", action="store_true", help="All-time for --wrapped (alias for --year all)")
    parser.add_argument("--cache", dest="cache_flag", action="store_true", help="Enable caching for --wrapped (saves to wrapped_cache)")
    parser.add_argument("--no-cache", dest="no_cache_flag", action="store_true", help="Disable caching for --wrapped (default)")
    args = parser.parse_args()

    if args.dashboard:
        import uvicorn
        from .server import app
        print(f"\n{CLR_VIBE}--- 👻 Ghost Dashboard Launching ---{CLR_RESET}")
        print(f"{CLR_DIM}Access your mission control at http://localhost:8000{CLR_RESET}")
        uvicorn.run(app, host="0.0.0.0", port=8000)
        return 0

    if args.setup:
        config = prompt_setup_config()
        config_path = save_user_config(config)
        print(f"\n{CLR_PRE}✅ Saved configuration to {config_path}{CLR_RESET}")
        return 0

    config = load_user_config()
    args = merge_runtime_settings(args, config)

    # Initialize the messaging provider (Default to iMessage for now)
    provider = IMessageProvider()

    if args.list_groups:
        groups = provider.get_recent_chats(limit=20)
        if not groups:
            print(f"{CLR_ERR}No recent group chats found.{CLR_RESET}")
            return 0
        print(f"\n{CLR_BOLD}Recent group chats:{CLR_RESET}")
        for idx, group in enumerate(groups, start=1):
            print(f"  {idx}. {group['label']} ({group['participant_count']} participants)")
        return 0

    if getattr(args, "wrapped", False):
        # Direct CLI mode: vibetexting --wrapped [--year YYYY|all] [--from YYYY] [--to YYYY] [--range YYYY-YYYY] [--all] [--cache/--no-cache]
        y_from = y_to = None
        err = None
        use_cache = False
        if getattr(args, "cache_flag", False) and getattr(args, "no_cache_flag", False):
            print(f"{CLR_ERR}Wrapped error: Can't use both --cache and --no-cache{CLR_RESET}")
            return 1
        if getattr(args, "cache_flag", False):
            use_cache = True
        elif getattr(args, "no_cache_flag", False):
            use_cache = False
        # Build synthetic arg_str from parsed args
        if getattr(args, "all_flag", False):
            y_from = y_to = None
        elif getattr(args, "range_year", None):
            val = getattr(args, "range_year")
            if val and "-" in str(val):
                a, b = str(val).split("-", 1)
                try:
                    y_from = int(a.strip()); y_to = int(b.strip())
                    if y_from > y_to:
                        err = f"--range {val} has start after end"
                except ValueError:
                    err = f"Invalid --range '{val}'"
            else:
                err = f"Invalid --range '{val}' (expected YYYY-YYYY)"
        elif getattr(args, "from_year", None) is not None or getattr(args, "to_year", None) is not None:
            try:
                if getattr(args, "from_year", None) is not None:
                    y_from = int(getattr(args, "from_year"))
                if getattr(args, "to_year", None) is not None:
                    y_to = int(getattr(args, "to_year"))
                if y_from is not None and y_to is not None and y_from > y_to:
                    err = f"--from {y_from} is after --to {y_to}"
            except ValueError as e:
                err = str(e)
        elif getattr(args, "year", None) is not None:
            val = getattr(args, "year")
            if isinstance(val, str) and val.lower() == "all":
                y_from = y_to = None
            else:
                try:
                    yv = int(val)
                    y_from = y_to = yv
                except ValueError:
                    err = f"Invalid --year '{val}'"
        else:
            y_from = y_to = 2026
        if err:
            print(f"{CLR_ERR}Wrapped error: {err}{CLR_RESET}")
            print(f"{CLR_DIM}Try: vibetexting --wrapped --year 2024  or  --range 2022-2024  or  --all [--cache]{CLR_RESET}")
            return 1
        print(f"{CLR_DIM}Computing your Wrapped…{CLR_RESET} {CLR_DIM}(cache={'on' if use_cache else 'off'}){CLR_RESET}")
        data = get_global_wrapped(year_from=y_from, year_to=y_to, use_cache=use_cache)
        # Non-interactive: print without pauses (session=None, but _print handles no-pause if we trick)
        # For direct CLI we print all cards without Enter pauses by monkey-patching _pause
        import builtins
        orig_input = builtins.input
        builtins.input = lambda *a, **k: ""
        # Also patch prompt_toolkit session if needed — _print_wrapped_story will call input fallback
        try:
            _print_wrapped_story(data, session=None)
        finally:
            builtins.input = orig_input
        return 0

    print(f"\n{CLR_VIBE}--- VibeText CLI (Local Mode) ---{CLR_RESET}")
    if config.get("__path__"):
        print(f"{CLR_DIM}Loaded defaults from {config['__path__']}{CLR_RESET}")
    print(f"{CLR_DIM}Type {CLR_RESET}/help{CLR_DIM} to see available commands.{CLR_RESET}")

    # Auto-start LLM server if needed (Business Tier: Seamless Experience)
    backend = (getattr(args, "backend", None) or "auto").lower()
    started_server = False
    if backend in {"auto", "lmstudio"}:
        print(f"{CLR_DIM}Checking local LLM server...{CLR_RESET}")
        if start_lmstudio_server():
            started_server = True
            print(f"{CLR_PRE}✅ Local LLM server is ready.{CLR_RESET}")
        else:
            # If backend is explicitly set to lmstudio, we should warn if it fails
            if backend == "lmstudio":
                print(f"{CLR_ERR}⚠️ Could not auto-start LM Studio server. Please ensure LM Studio is open and the 'lms' CLI is installed.{CLR_RESET}")

    chat_filter = args.chat
    pinned_chat_id = None
    first_run = True
    goal = None
    autopilot_active = False

    # Set up command completer for prompt-toolkit
    commands = [
        "/chat", "/groups", "/model", "/models", "/limit", "/delay", "/full",
        "/goal", "/auto", "/vibe", "/wrapped", "/paste", "/help", "exit", "quit"
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
                    original = session.prompt(ANSI(f"{CLR_PRE}vibetext{prompt_label}{CLR_RESET}> ")).strip()
                
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

                if cmd.startswith('/wrapped'):
                    # Extract args after /wrapped
                    arg_str = original[8:].strip()  # len("/wrapped")==8
                    y_from, y_to, use_cache, show_help, err = _parse_wrapped_args(arg_str)
                    if err:
                        print(f"{CLR_ERR}Wrapped error: {err}{CLR_RESET}")
                        print(f"{CLR_DIM}Try /wrapped --help for options{CLR_RESET}")
                        first_run = False
                        continue
                    if show_help:
                        print_wrapped_help()
                        first_run = False
                        continue
                    print(f"{CLR_DIM}Computing your Wrapped…{CLR_RESET} {CLR_DIM}(cache={'on' if use_cache else 'off'}){CLR_RESET}")
                    try:
                        data = get_global_wrapped(year_from=y_from, year_to=y_to, use_cache=use_cache)
                        _print_wrapped_story(data, session=session)
                    except KeyboardInterrupt:
                        print(f"\n{CLR_DIM}Wrapped interrupted.{CLR_RESET}")
                    except Exception as e:
                        print(f"{CLR_ERR}Failed to build Wrapped: {e}{CLR_RESET}")
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
                    if not chat_filter:
                        chat_filter = session.prompt(ANSI(f"\n{CLR_USR}Who are you texting?{CLR_RESET} ")).strip() or None
                    
                    if chat_filter:
                        autopilot_active = True
                        try:
                            goal = run_autopilot(args, config, chat_filter, vibe_content, goal, provider, session=session, pinned_chat_id=pinned_chat_id)
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
                    pinned_chat_id = None
                    print(f"{CLR_PRE}✅ Recipient switched to '{chat_filter}'{CLR_RESET}")
                    first_run = False
                    continue

                if cmd == '/groups':
                    groups = provider.get_recent_chats(limit=10)
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
                                selected_group = groups[selected_idx - 1]
                                chat_filter = selected_group["label"]
                                pinned_chat_id = selected_group["chat_id"]
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
                print(f"{CLR_DIM}Searching history for '{chat_filter}'...{CLR_RESET}")
                chat_history, message_count, resolved_chat_label, is_group_chat, chat_context, chat_id, chat_guid, _ = provider.load_history(chat_filter, args.history_limit, chat_id=pinned_chat_id)
                if chat_history:
                    label = resolved_chat_label or chat_filter
                    print(f"{CLR_PRE}✅ Loaded {message_count} messages from '{label}'{CLR_RESET}")
                else:
                    print(f"{CLR_DIM}No history found. Continuing without context.{CLR_RESET}")

            first_run = False

            # Search for relevant old memories based on keywords in the current message
            memories = None
            if chat_id and original and not original.startswith('/'):
                memories = provider.search_memories(chat_id, original)
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

            feedback_notes = load_feedback_notes()
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
                goal,
                feedback_notes,
            )
            reply = call_local_llm(prompt, model, backend)

            print(f"\n{CLR_VIBE}{'='*40}{CLR_RESET}")
            print(f"{CLR_BOLD}SUGGESTED REPLY:{CLR_RESET}")
            print(f"{CLR_DIM}{'-'*40}{CLR_RESET}")
            print(reply)
            print(f"{CLR_VIBE}{'='*40}{CLR_RESET}")

            if "Error" not in reply:
                # --- Vibe Match Eval ---
                if vibe_content:
                    try:
                        vibe_score = score_vibe_match(reply, vibe_content)
                        print_vibe_score(vibe_score)
                    except Exception:
                        pass

                try:
                    subprocess.run(['pbcopy'], input=reply, encoding='utf-8')
                    print(f"{CLR_DIM}(Copied to clipboard! 📋){CLR_RESET}")
                except Exception:
                    pass

                # --- Random feedback prompt (~25% chance) ---
                maybe_ask_feedback(reply)

            print()

    except KeyboardInterrupt:
        pass
    finally:
        # Stop the Gemma server if we started it
        if started_server:
            print(f"\n{CLR_DIM}Stopping Gemma server...{CLR_RESET}")
            stop_lmstudio_server()
            print(f"{CLR_PRE}✅ Server stopped.{CLR_RESET}")

if __name__ == "__main__":
    main()
