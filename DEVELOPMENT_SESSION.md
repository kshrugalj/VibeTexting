# Building VibeTexting: From a Crazy Idea to a Working Product

**A coding agent session log — the kind you're proud of.**

---

## How It Started

Honestly, it started with a stupid problem. I was drowning in text messages. Not like, important business messages — just friends, group chats, people asking "you coming tonight?" and "yo did you see that meme." I'd see 15 unread notifications, and by the time I got to them, the conversation moved on. I was either responding too late or copy-pasting the same "yeah I'm down" to everyone.

I thought: what if a local AI could just... text like me? Not in a scammy bot way. In a "this is actually how I talk" way. And what if it ran entirely on my laptop so nobody's data ever leaves my machine?

That was April 19, 2026. VibeTexting was born.

---

## Phase 1: The Ugly Prototype (Week 1)

The first version was rough. Like, really rough.

**What I built:** A Python script that read my iMessage database, pulled out messages I'd sent, and fed them to a local LLM as few-shot examples. Then it would generate replies that sounded like me.

**The stack at this point:**
- Python 3.8+
- SQLite (reading macOS `~/Library/Messages/chat.db` directly)
- Ollama for local inference (llama3)
- A single `vibetext.py` script — maybe 80 lines

**The first problem I hit:** macOS won't let you read `chat.db` without Full Disk Access. I spent 2 hours wondering why my script kept returning empty results before I realized the terminal needed explicit permission in System Settings > Privacy & Security. That's when I learned that "truly local" also means "truly constrained by OS security."

**The vibe extraction problem:** How do you teach an AI to sound like you? I tried a few approaches:
1. **Keyword matching** — Terrible. "lol" and "haha" are universal. This told the AI nothing about *my* style.
2. **Sentiment analysis** — Way too abstract. Knowing I'm "positive" doesn't help when I need to know I use lowercase, skip periods, and overuse "nvm."
3. **Few-shot examples from actual messages** — This is what worked. I query the database for messages I've sent (`is_from_me = 1`), filter out tapbacks, URLs, attachments, and Apple auto-generated messages, then sample 150 of them. That's my "vibe profile."

```python
# The core extraction query — simple but effective
query = """
    SELECT m.text, m.date
    FROM message m
    WHERE m.is_from_me = 1
      AND m.text IS NOT NULL
      AND length(m.text) > 2
      AND length(m.text) < 300
      AND m.text NOT LIKE '%http%'
      AND m.associated_message_guid IS NULL
    ORDER BY m.date DESC
    LIMIT 5000
"""
```

**What worked:** The AI could actually mimic my texting style. Not perfectly, but well enough that friends couldn't tell the difference in blind tests.

**What didn't work:** The prompt was enormous. Feeding 150 examples plus chat history plus the incoming message plus instructions meant the context window filled up fast. Llama3's 4K token limit was a real constraint. I had to aggressively truncate the vibe profile to ~2000 characters.

---

## Phase 2: Auto-Pilot Mode (Week 2)

The original idea was just "generate a reply, I'll copy-paste it." But then I thought: what if it could just... send the reply itself?

**The auto-pilot loop:**
1. Poll the iMessage database every 5 seconds
2. Detect new incoming messages
3. Wait a configurable delay (to seem human)
4. Build a prompt with vibe profile + chat history + conversation goal
5. Generate reply via local LLM
6. Send via AppleScript

**The AppleScript nightmare:** Sending messages through AppleScript is fragile. The first version tried to find a buddy by phone number:
```applescript
tell application "Messages"
    set targetService to 1st service whose service type is iMessage
    set targetBuddy to buddy recipientId of targetService
    send msg to targetBuddy
end tell
```

This broke constantly. Sometimes it would create duplicate chats. Sometimes it couldn't find the buddy. For group chats, it was impossible — AppleScript doesn't have a clean API for "send to this group chat."

**The fix:** I discovered you can target chats by their `chat_identifier` (GUID). The iMessage database stores this, and you can use it to target existing conversations directly:
```applescript
tell application "Messages"
    set targetChat to (1st chat whose id is chatId)
    send msg to targetChat
end tell
```

This was a game-changer. No more duplicate chats. Group chats just worked. But getting the GUID right required understanding Apple's internal chat identifier format, which is essentially `iMessage;+;{phone_number}` for DMs or `iMessage;+;{phone1},{phone2}` for groups.

**The typing delay problem:** If the AI responds instantly, it's obviously a bot. I implemented a natural typing simulation:
```python
typing_speed_factor = 0.08  # seconds per character (~12 chars/sec)
typing_delay = len(reply) * typing_speed_factor
total_delay = base_delay + typing_delay
```

A 50-character reply takes ~4 seconds. A 100-character reply takes ~8 seconds. Combined with a configurable base delay, this made responses feel human.

---

## Phase 3: The Architecture Overhaul (Week 3)

By now the code was a mess. Everything was in one file. The CLI had grown to 600+ lines. Adding new features meant wading through spaghetti.

**The refactor:** I restructured the entire codebase into a proper Python package:

```
vibetexting/
├── providers/          # Platform connectors
│   ├── base.py         # Abstract base class
│   └── imessage.py     # iMessage implementation
├── server.py           # FastAPI backend
├── database.py         # ChromaDB (RAG) + SQLite
├── vision.py           # Image analysis
├── cli.py              # Main interactive loop
├── prompts.py          # Prompt engineering
├── llm.py              # LLM API integrations
├── config.py           # User configuration
├── contacts.py         # macOS Contacts sync
├── evals.py            # Vibe match scoring
├── feedback.py         # Style correction system
└── utils.py            # AppleScript + helpers
```

**The provider abstraction was critical.** By creating a `BaseMessagingProvider` interface, I made it possible to add WhatsApp, Signal, or Telegram support without rewriting the core logic:

```python
class BaseMessagingProvider(ABC):
    @abstractmethod
    def load_history(self, chat_filter, limit=None, **kwargs) -> Tuple:
        pass
    
    @abstractmethod
    def send_message(self, recipient, text, **kwargs) -> bool:
        pass
    
    @abstractmethod
    def get_recent_chats(self, limit=10) -> List[Dict]:
        pass
    
    @abstractmethod
    def search_memories(self, chat_id, query, limit=5) -> str:
        pass
```

iMessage was just the first implementation. The architecture is ready for WhatsApp and Signal — that's the next phase.

**Multi-backend LLM support:** Not everyone wants to use Ollama. I added LM Studio support with automatic server startup/shutdown:

```python
def call_local_llm(prompt, model="llama3", backend="auto"):
    # Auto: prefer LM Studio for Gemma-family, otherwise Ollama
    if "gemma" in model.lower():
        start_lmstudio_server(model)
        reply = call_lmstudio(prompt, model)
        if not reply.startswith("Error"):
            return reply
        return call_ollama(prompt, model)  # fallback
    
    reply = call_ollama(prompt, model)
    if not reply.startswith("Error"):
        return reply
    
    start_lmstudio_server(model)
    return call_lmstudio(prompt, model)  # fallback
```

The auto-fallback logic means users don't need to think about which backend to use. If one fails, it tries the other.

---

## Phase 4: Semantic Memory (RAG 2.0) (Week 4)

Keyword-based memory was too literal. If someone texts "remember that time at the beach?" the old system would search for messages containing "beach" — which might return nothing if you used different words.

**The ChromaDB integration:** I switched to vector embeddings using `sentence-transformers` with the `all-MiniLM-L6-v2` model (384-dimensional embeddings, runs locally):

```python
chroma_client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
message_collection = chroma_client.get_or_create_collection(
    name="messages",
    embedding_function=embedding_func,
    metadata={"hnsw:space": "cosine"}
)
```

**How it works:**
1. When you load a chat, messages are indexed into ChromaDB with metadata (chat_id, speaker, timestamp)
2. When you receive a new message, the system searches for semantically similar past messages
3. These "memories" are injected into the prompt so the AI has context

**The indexing problem:** ChromaDB needs to index messages, but doing it on every message load is slow. I implemented a high-water mark approach:
- Track the latest indexed timestamp per chat
- Only index new messages since the last sync
- Cache everything persistently in `~/.vibetexting/chroma_db/`

**The fallback chain:** If ChromaDB isn't installed, the system falls back to keyword search. If keywords fail, it just uses the recent chat history. The system degrades gracefully.

---

## Phase 5: Vision Support (Week 5)

iMessage isn't just text. People send memes, screenshots, photos. The AI needed to "see" these.

**The LLaVA integration:** I used Ollama's LLaVA model for local image description:

```python
def describe_image(image_path):
    base64_image = _encode_image(image_path)
    payload = {
        "model": "llava",
        "prompt": "Briefly describe this image in one short sentence.",
        "images": [base64_image]
    }
    # Call Ollama API...
```

**The caching problem:** Describing the same image twice is wasteful. I implemented a persistent cache using MD5 hashes of image paths:
```python
VISION_CACHE_DIR = os.path.expanduser("~/.vibetexting/vision_cache")

def _get_cache_path(image_path):
    name_hash = hashlib.md5(image_path.encode()).hexdigest()
    return os.path.join(VISION_CACHE_DIR, f"{name_hash}.txt")
```

**The attributedBody problem:** Some iMessage messages store text in a binary plist format (`attributedBody`) rather than the plain text field. I had to write a parser that finds the NSString marker in the binary data and extracts the readable text:

```python
if "NSString" in body_str:
    parts = attr_body.split(b"NSString", 1)
    if len(parts) > 1:
        sub = parts[1]
        for i in range(len(sub) - 1):
            if sub[i] == 0x01 and sub[i+1] == 0x2b:
                start = i + 3
                end = start
                while end < len(sub) and (sub[end] >= 0x20 or sub[end] == 0x0a):
                    end += 1
                cleaned = sub[start:end].decode('utf-8', errors='ignore')
```

This was reverse-engineered from observing the binary format. It's not perfect, but it catches most messages that would otherwise show as empty.

---

## Phase 6: Contact Intelligence (Week 5)

The system needed to understand *who* you're talking to, not just match strings.

**Two extraction methods:**
1. **Fast SQLite** — Direct read from macOS AddressBook database:
   ```python
   db_path = os.path.expanduser(
       "~/Library/Application Support/AddressBook/**/AddressBook-v22.abcddb"
   )
   ```
   This is ~100x faster than AppleScript but requires Full Disk Access.

2. **AppleScript fallback** — Slower but doesn't need special permissions:
   ```applescript
   tell application "Contacts"
       set people_list to people
       -- iterate and extract...
   end tell
   ```

**Fuzzy matching:** Users don't type phone numbers perfectly. "mom" should match "Mom" +1-555-0123. I implemented Levenshtein distance matching with normalization:

```python
def fuzzy_name_match(search_term, field_value):
    s1 = normalize_chat_key(search_term)  # strips non-alphanumeric, lowercases
    s2 = normalize_chat_key(field_value)
    if s1 == s2:
        return 100.0
    if s1 in s2 or s2 in s1:
        return 85.0
    distance = levenshtein_distance(s1, s2)
    return (1 - distance / max(len(s1), len(s2))) * 100
```

This handles nicknames, partial numbers, and common abbreviations.

---

## Phase 7: The Ghost Dashboard (Week 6)

The CLI was powerful but not accessible. I wanted a web UI that felt like a mission control center.

**The stack:**
- **Backend:** FastAPI (Python) — serves the API and static files
- **Frontend:** React 19 + Vite + Tailwind CSS 4
- **Design:** "GHOST_OS" aesthetic — dark, stealthy, monospace-heavy

**The design philosophy:**
```css
/* GHOST_OS System Colors */
--ghost-900: #0a0a0c;    /* Deep void */
--gold-accent: #D4AF37;   /* Mission-critical data */
--status-pulse: #22c55e;  /* Live connection indicator */
```

The UI uses small monospace labels (10px), chrome-reflect gradients, and gold accents to create a "low-level system terminal" feel. Everything is dim until hovered or active — stealth first.

**The autopilot toggle:** The dashboard exposes the auto-pilot as a REST API:
```python
@app.post("/api/autopilot/toggle")
async def toggle_autopilot(req: AutopilotToggleRequest, background_tasks: BackgroundTasks):
    # Start/stop background polling loop per chat
    background_tasks.add_task(_autopilot_loop, chat_id, req.chat_filter, req.goal)
```

The React frontend polls `/api/autopilot/status` every 5 seconds and shows a pulsing green indicator for active auto-pilots.

---

## Phase 8: Evaluation and Feedback (Week 7)

How do you know if the AI actually sounds like you? I built a multi-signal scoring system.

**Four sub-signals (each 0-100):**

1. **Semantic Similarity (40%)** — Cosine distance between reply embedding and vibe profile embeddings. Uses the same `all-MiniLM-L6-v2` model as ChromaDB.

2. **Length Match (20%)** — How close is the reply word count to your median message length? A 50-word reply when you usually text in 5 words is flagged.

3. **Formality Penalty (25%)** — Deducts points for AI-sounding phrases:
   ```python
   _FORMAL_PATTERNS = [
       r"\bI hope this (message )?finds you\b",
       r"\bplease don't hesitate\b",
       r"\bcertainly\b",
       r"\babsolutely\b",
       r"\bAs an AI\b",
       # ... 20+ patterns
   ]
   ```

4. **Lexical Overlap (15%)** — What fraction of reply tokens appear in your actual vocabulary?

**Baseline calibration:** The raw score is normalized against a baseline computed from *your own messages*. If your messages score ~70 against each other, and the AI scores ~65, that's actually quite good (93% of baseline). This prevents false negatives where the AI sounds like you but the score seems low.

**The feedback loop:** Every ~25% of replies, the system asks for feedback:
```
Was that reply on-brand for you?  y / n / f(feedback) / skip
```

If you say "n" or type a correction, it's saved to `~/.vibetexting_feedback.json` and injected into future prompts:
```python
feedback_block = (
    f"\n\nStyle corrections from past feedback — apply these:\n"
    f"{feedback_notes}"
)
```

This creates a continuous improvement loop without retraining.

---

## The Technical Decisions That Mattered

### Why Local-First?
Cloud APIs (OpenAI, Anthropic) are easier. But:
- **Privacy:** Text messages are deeply personal. Sending them to a cloud API is a non-starter for many users.
- **Cost:** Running llama3 locally is free. Cloud APIs cost money per token.
- **Latency:** No network round-trip. Response generation is as fast as your GPU/CPU.

### Why ChromaDB Over SQLite FTS?
Full-text search in SQLite works but is keyword-based. "Remember that time" won't match "that evening we hung out." Vector embeddings capture semantic meaning. ChromaDB runs locally, stores persistently, and integrates cleanly with sentence-transformers.

### Why AppleScript for Sending?
There's no other way to send iMessages programmatically on macOS. The Messages app doesn't have a public API. AppleScript is the official automation layer, even though it's fragile.

### Why the Provider Abstraction?
iMessage was the starting point, but the vision is multi-platform. The `BaseMessagingProvider` interface means adding WhatsApp (via whatsapp-web.js) or Signal (via signal-cli) requires implementing four methods, not rewriting the entire system.

---

## The Numbers

| Metric | Value |
|--------|-------|
| Lines of Python | ~3,200 |
| Lines of TypeScript/React | ~270 |
| Dependencies (Python) | 5 core + 2 optional |
| Dependencies (JS) | 2 core + 12 dev |
| Local LLM models supported | Ollama, LM Studio |
| Vision model | LLaVA via Ollama |
| Embedding model | all-MiniLM-L6-v2 |
| Vector DB | ChromaDB (local) |
| Database | SQLite (iMessage chat.db) |
| API framework | FastAPI |
| Frontend | React 19 + Vite + Tailwind 4 |
| Platform | macOS (iMessage) |

---

## What's Next

1. **WhatsApp support** — Using the provider abstraction, this is the natural next step.
2. **Background service** — Run as a launchd daemon instead of a foreground process.
3. **Multi-device sync** — Share vibe profiles and memories across machines.
4. **Conversation analytics** — Dashboard insights on response times, sentiment trends, most active contacts.



*Built from April 19 to June 25, 2026. From a single Python script to a full-stack product with semantic memory, vision support, and a mission control dashboard. Every bug fixed at 2 AM, every edge case discovered the hard way, every feature earned through iteration.*
