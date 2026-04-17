import re
from typing import Optional

MANUAL_RESPONSE_PATTERNS = [
    r"\bdo you want to\b",
    r"\bwanna\b",
    r"\bwant to hang out\b",
    r"\bhang out\b",
    r"\bget together\b",
    r"\bmeet up\b",
    r"\bare you free\b",
    r"\bwhat do you want to do\b",
    r"\bshould we\b",
    r"\bwhat time works\b",
    r"\bavailable\b",
    r"\bcan you\b",
    r"\bwould you like to\b",
    r"\bopinion\b",
    r"\bdecision\b",
]

def classify_response_type(message: str) -> str:
    lowered_message = (message or "").lower()
    if any(phrase in lowered_message for phrase in ["hang out", "get together", "meet up", "do you want to", "wanna", "are you free", "should we", "what time works"]):
        return "plan"
    if any(phrase in lowered_message for phrase in ["can you", "could you", "would you", "please", "help me"]):
        return "request"
    if any(word in lowered_message for word in ["yes or no", "either", "which one", "choose", "decision"]):
        return "choice"
    return "general"

def build_intent_suggestions(original: str) -> list[str]:
    response_type = classify_response_type(original)
    if response_type == "plan":
        return [
            "Yes, that sounds good.",
            "I can’t tonight.",
            "Maybe another time.",
            "Let me check and get back to you.",
        ]
    if response_type == "request":
        return [
            "Sure, I can do that.",
            "I might be able to, but I need a minute.",
            "I can’t right now.",
            "Can you give me a little more info?",
        ]
    if response_type == "choice":
        return [
            "Pick the first one.",
            "Pick the second one.",
            "I’m not sure yet.",
            "Whichever is easiest.",
        ]
    return ["Yep.", "Nope.", "Maybe.", "I’ll think about it."]

def needs_manual_response(message: str) -> bool:
    lowered_message = (message or "").lower()
    if not lowered_message:
        return False
    for pattern in MANUAL_RESPONSE_PATTERNS:
        if re.search(pattern, lowered_message):
            return True
    return False

def is_question_message(message: str) -> bool:
    lowered_message = (message or "").strip().lower()
    if not lowered_message:
        return False
    if lowered_message.endswith("?"):
        return True
    question_starts = (
        "what ",
        "when ",
        "where ",
        "why ",
        "who ",
        "how ",
        "are you ",
        "is it ",
        "is this ",
        "do you ",
        "did you ",
        "can you ",
        "could you ",
        "would you ",
        "should you ",
        "will you ",
        "am i ",
        "can i ",
        "could i ",
        "would i ",
        "should i ",
    )
    return lowered_message.startswith(question_starts)

def prompt_for_intent(original: str) -> str:
    print("\nThis message looks like it needs your real intent before a reply is drafted.")
    print(f"Message: {original}")
    intent = input("What do you want to say? ").strip()
    return intent

def prompt_for_intent_choice(original: str) -> str:
    suggestions = build_intent_suggestions(original)
    print("\nThis message looks like it needs your intent. Choose the closest response type:")
    print(f"Message: {original}")
    for index, suggestion in enumerate(suggestions, start=1):
        print(f"  {index}. {suggestion}")
    print(f"  {len(suggestions) + 1}. Write my own")
    while True:
        choice = input(f"Select (1-{len(suggestions) + 1}): ").strip()
        if not choice:
            continue
        try:
            selected_index = int(choice)
            if 1 <= selected_index <= len(suggestions):
                return suggestions[selected_index - 1]
            if selected_index == len(suggestions) + 1:
                return prompt_for_intent(original)
        except ValueError:
            continue

def prompt_for_barebones_answer(original: str) -> str:
    print("\nThis looks like a question. Give the bare bones answer you want to say back.")
    print(f"Message: {original}")
    answer = input("Bare bones answer: ").strip()
    return answer

def build_prompt(
    original: str,
    vibe_profile: Optional[str] = None,
    chat_history: Optional[str] = None,
    chat_label: Optional[str] = None,
    chat_context: Optional[str] = None,
    user_name: Optional[str] = None,
    user_intent: Optional[str] = None,
    user_barebones_answer: Optional[str] = None,
    memories: Optional[str] = None,
    goal: Optional[str] = None,
) -> str:
    # 1. Start with the core instructions
    system_setup = "You are an AI assistant helping someone respond to a text message."
    if vibe_profile:
        # Aggressive trim to stay within 4096 tokens
        max_vibe_chars = 2000
        if len(vibe_profile) > max_vibe_chars:
            vibe_profile = vibe_profile[:max_vibe_chars] + "... (truncated)"
        system_setup = (
            "You are an AI assistant that mimics my exact texting style.\n\n"
            f"Here are examples of messages I have sent:\n{vibe_profile}\n\n"
            "Use the EXACT same vocabulary, capitalization style, phrasing, and punctuation habits as the examples above."
        )
    
    identity_block = ""
    if user_name:
        identity_block = (f"\n\nThe user's name is {user_name}."
                          f" If someone asks for your name or who you are, answer with '{user_name}'.")
    
    intent_block = ""
    if user_intent:
        intent_block = f"\n\nThe user wants to say this in response: {user_intent}"
    if user_barebones_answer:
        intent_block = f"\n\nThe user gave this bare-bones answer to the question: {user_barebones_answer}"

    # 2. Build the history block with smart trimming
    # Character budget reduced to 2500 to leave room for Memories and instructions
    history_block = ""
    if chat_history:
        label = f" for {chat_label}" if chat_label else ""
        
        # Keep the LATEST messages
        max_history_chars = 2500 
        if len(chat_history) > max_history_chars:
            # Find a newline to avoid cutting a message in half
            cut_index = len(chat_history) - max_history_chars
            next_newline = chat_history.find("\n", cut_index)
            if next_newline != -1:
                chat_history = "... (older history omitted)\n" + chat_history[next_newline:].strip()
            else:
                chat_history = "... (older history omitted)\n" + chat_history[cut_index:].strip()
                
        history_block = f"\n\nHere is the recent conversation history{label}:\n{chat_history}"
    
    if chat_context:
        history_block += f"\n\n{chat_context}"

    memory_block = ""
    if memories:
        memory_block = f"\n\nImportant memories from past conversations:\n{memories}"

    goal_block = ""
    if goal:
        goal_block = f"\n\nYour overarching GOAL for this conversation is: {goal}.\n" \
                     f"Steer the conversation naturally towards this outcome."

    return f"""{system_setup}{identity_block}{history_block}{memory_block}{goal_block}{intent_block}

Incoming message: "{original}"

Generate a natural, human-like text response that matches my style and the conversation context.
CRITICAL: Limit your response to 1-2 short sentences maximum. Do not be overly verbose.
CRITICAL: DO NOT use excessive emojis. Only use them sparingly if heavily present in the vibe profile.
CRITICAL: DO NOT repeat phrases, jokes, or structures you have already used in the recent history.
NEVER sound like a formal AI assistant; use casual, human texting vernacular.
If there is no exact example in the vibe profile, improvise a plausible answer that still sounds like the same person.
If the message is a direct question, answer the actual question first and clearly.
Answer the message the way a real person would in normal conversation, whether it is a question, statement, joke, or follow-up.
Do not respond with dismissive filler like "idk", "lol", or vague deflections unless that is clearly the style in the examples.
If no name is configured, do not invent one or refer to yourself as an assistant; just answer naturally in the same voice.
If the user provided an intent sentence, treat that as the meaning to preserve and rewrite it in the user's texting style.
If the user provided a bare-bones answer, treat that as the content to preserve and rewrite it in the user's texting style.
If this is a group chat, reply in a way that fits the latest speaker and group context naturally.
Keep it concise and appropriate for a text message.
Response:"""
