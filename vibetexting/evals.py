"""
evals.py — Vibe Match Evaluator
================================
Scores a generated reply against the user's vibe profile to answer:
"Does this actually sound like me?"

Four sub-signals (each 0–100):
  1. Semantic Similarity  — cosine distance via SentenceTransformer (same
                            model already used by ChromaDB RAG).
  2. Length Match         — how close is reply length to median message length?
  3. Formality Penalty    — deducts points for AI-sounding phrases never in
                            your vibe profile.
  4. Lexical Overlap      — unigram overlap with your actual vocabulary.

The raw weighted score is normalised against a *baseline* computed from the
user's own messages, so genuine user messages land near 100 and the displayed
grade reflects closeness to the user's real style rather than an absolute
threshold.
"""

from __future__ import annotations

import re
import statistics
from typing import Optional

# ---------------------------------------------------------------------------
# Phrases that mark formal / AI-assistant tone – penalise heavily if found.
# ---------------------------------------------------------------------------
_FORMAL_PATTERNS = [
    r"\bI hope this (message )?finds you\b",
    r"\bplease don't hesitate\b",
    r"\bfeel free to\b",
    r"\bI apologize\b",
    r"\bI understand your concern\b",
    r"\bthank you for reaching out\b",
    r"\bcertainly\b",
    r"\babsolutely\b",
    r"\bOf course[,!]?\b",
    r"\bI'd be happy to\b",
    r"\bAs an AI\b",
    r"\bI am an AI\b",
    r"\bI cannot\s+(assist|help|provide|do that|support)\b",
    r"\bI must\b",
    r"\bplease note\b",
    r"\bkindly\b",
    r"\bregards\b",
    r"\bsincerely\b",
    r"\bbest regards\b",
    r"\bthank you for your\b",
    r"\bI would like to\b",
    r"\bI am pleased\b",
    r"\bI am writing\b",
    r"\bIt is important to\b",
    r"\bI want to ensure\b",
    r"\bI want to make sure\b",
]
_FORMAL_RE = [re.compile(p, re.IGNORECASE) for p in _FORMAL_PATTERNS]


# ---------------------------------------------------------------------------
# Try to import SentenceTransformer for semantic scoring.
# Falls back to lexical-only mode if unavailable.
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    _EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
    _embed_model: Optional[SentenceTransformer] = None  # lazy-loaded

    def _get_embed_model() -> SentenceTransformer:
        global _embed_model
        if _embed_model is None:
            _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
        return _embed_model

    def _cosine(a: "np.ndarray", b: "np.ndarray") -> float:
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    SEMANTIC_AVAILABLE = True

except ImportError:
    SEMANTIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stripping punctuation."""
    return re.findall(r"\b[a-z']+\b", text.lower())


def _parse_vibe_samples(vibe_text: str) -> list[str]:
    """
    Split vibe profile into individual message samples.
    Each non-empty line is one message (matches how extract_imessage_vibe writes it).
    """
    lines = [ln.strip() for ln in vibe_text.splitlines()]
    return [ln for ln in lines if ln]


def _median_word_count(samples: list[str]) -> float:
    counts = [len(s.split()) for s in samples]
    return statistics.median(counts) if counts else 5.0


def _build_vocab(samples: list[str]) -> set[str]:
    vocab: set[str] = set()
    for s in samples:
        vocab.update(_tokenize(s))
    return vocab


# ---------------------------------------------------------------------------
# Sub-signal scorers (each returns 0–100)
# ---------------------------------------------------------------------------

def _score_semantic(reply: str, samples: list[str]) -> Optional[float]:
    """
    Mean cosine similarity between the reply embedding and a random selection
    of up to 50 vibe profile sample embeddings.  Returns None if unavailable.
    """
    if not SEMANTIC_AVAILABLE or not samples:
        return None

    model = _get_embed_model()

    # Sample up to 50 examples to keep it fast
    import random
    selected = random.sample(samples, min(50, len(samples)))

    reply_emb = model.encode(reply, convert_to_numpy=True)
    sample_embs = model.encode(selected, convert_to_numpy=True)

    sims = [_cosine(reply_emb, se) for se in sample_embs]
    mean_sim = statistics.mean(sims)  # cosine similarity ∈ [-1, 1]

    # Normalise to 0–100.  Typical same-style messages score ~0.3–0.7.
    # We clamp and scale so 0.5 → 100, 0.0 → 0.
    score = max(0.0, min(1.0, mean_sim / 0.5)) * 100
    return round(score, 1)


def _score_length(reply: str, samples: list[str]) -> float:
    """
    How close is the reply word count to the user's median message length?
    Perfect match → 100, ≥3× off → 0.
    """
    if not samples:
        return 50.0

    reply_wc = len(reply.split())
    median_wc = _median_word_count(samples)
    if median_wc == 0:
        return 50.0

    ratio = reply_wc / median_wc
    # Penalise in both directions: too short or too long
    if ratio <= 0:
        return 0.0
    deviation = abs(ratio - 1.0)  # 0 = perfect, >2 = very far off
    score = max(0.0, 1.0 - (deviation / 2.0)) * 100
    return round(score, 1)


def _score_formality(reply: str) -> float:
    """
    Returns 100 if no formal patterns are detected; deducts 25 per hit,
    flooring at 0.
    """
    hits = sum(1 for p in _FORMAL_RE if p.search(reply))
    return max(0.0, 100.0 - hits * 25)


def _score_lexical(reply: str, vocab: set[str]) -> float:
    """
    Fraction of reply tokens that appear in the user's vocabulary, scaled to
    0–100.  Stop-words are excluded from the calculation to focus on
    distinctive vocabulary.
    """
    _STOP = {
        "i", "a", "the", "is", "it", "to", "and", "of", "in", "you",
        "that", "me", "my", "we", "was", "are", "for", "on", "do",
        "be", "have", "he", "she", "they", "this", "with", "at", "or",
        "an", "but", "not", "so", "if", "as", "up", "by", "he", "no",
        "its", "our", "out", "has", "had", "his", "her", "can", "did",
        "get", "got", "just", "like", "what", "how", "when", "where",
        "who", "why", "will", "would", "could", "should", "about",
    }
    tokens = [t for t in _tokenize(reply) if t not in _STOP]
    if not tokens:
        return 50.0

    overlap = sum(1 for t in tokens if t in vocab)
    return round((overlap / len(tokens)) * 100, 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_WEIGHTS = {
    "semantic":  0.40,
    "length":    0.20,
    "formality": 0.25,
    "lexical":   0.15,
}


def _raw_score(reply: str, samples: list[str], vocab: set[str]) -> float:
    """Compute the raw weighted score (0–100) for a single reply."""
    sem  = _score_semantic(reply, samples)
    leng = _score_length(reply, samples)
    form = _score_formality(reply)
    lex  = _score_lexical(reply, vocab)

    if sem is None:
        w_sem, w_lex = 0.0, _WEIGHTS["lexical"] + _WEIGHTS["semantic"]
    else:
        w_sem, w_lex = _WEIGHTS["semantic"], _WEIGHTS["lexical"]

    return (
        (sem or 0) * w_sem
        + leng * _WEIGHTS["length"]
        + form * _WEIGHTS["formality"]
        + lex  * w_lex
    )


def compute_vibe_baseline(vibe_text: str, n_samples: int = 15) -> float:
    """
    Score *n_samples* of the user's own messages against the rest of their
    vibe profile.  The average raw score is the "ceiling" — what a perfectly
    on-brand reply looks like.  Cached after first call per vibe_text hash.
    """
    import hashlib, functools

    key = hashlib.md5(vibe_text.encode()).hexdigest()
    cached = _baseline_cache.get(key)
    if cached is not None:
        return cached

    import random
    samples = _parse_vibe_samples(vibe_text)
    if len(samples) < 4:
        _baseline_cache[key] = 70.0
        return 70.0

    selected = random.sample(samples, min(n_samples, len(samples)))
    scores = []
    for msg in selected:
        rest = [s for s in samples if s != msg]
        vocab = _build_vocab(rest)
        scores.append(_raw_score(msg, rest, vocab))

    baseline = statistics.mean(scores) if scores else 70.0
    _baseline_cache[key] = baseline
    return baseline


_baseline_cache: dict[str, float] = {}


def score_vibe_match(reply: str, vibe_text: str) -> dict:
    """
    Score *reply* against *vibe_text* (the raw vibe profile content).

    The raw weighted score is normalised against the baseline score of the
    user's own messages so that on-brand replies approach 100 and the grade
    reflects proximity to the user's real style.

    Returns a dict::

        {
            "overall": float,          # 0–100, normalised against baseline
            "raw": float,              # raw weighted score before normalisation
            "baseline": float,         # reference score from user's own messages
            "semantic": float | None,
            "length": float,
            "formality": float,
            "lexical": float,
            "grade": str,              # "A" / "B" / "C" / "D" / "F"
            "label": str,
        }
    """
    samples = _parse_vibe_samples(vibe_text)
    vocab   = _build_vocab(samples)

    sem  = _score_semantic(reply, samples)
    leng = _score_length(reply, samples)
    form = _score_formality(reply)
    lex  = _score_lexical(reply, vocab)

    raw = round(_raw_score(reply, samples, vocab), 1)

    # Normalise: express score as % of what the user's own messages score.
    # Clamp to 100 so a perfect imitation doesn't go over.
    baseline  = compute_vibe_baseline(vibe_text)
    if baseline > 0:
        normalised = round(min(100.0, raw / baseline * 100), 1)
    else:
        normalised = raw

    if normalised >= 85:
        grade, label = "A", "Sounds like you ✅"
    elif normalised >= 70:
        grade, label = "B", "Mostly your vibe 👍"
    elif normalised >= 55:
        grade, label = "C", "Somewhat like you 🤔"
    elif normalised >= 38:
        grade, label = "D", "Off-brand ⚠️"
    else:
        grade, label = "F", "Doesn't sound like you ❌"

    return {
        "overall":   normalised,
        "raw":       raw,
        "baseline":  round(baseline, 1),
        "semantic":  sem,
        "length":    leng,
        "formality": form,
        "lexical":   lex,
        "grade":     grade,
        "label":     label,
    }


# ---------------------------------------------------------------------------
# CLI display helper
# ---------------------------------------------------------------------------

def print_vibe_score(score: dict) -> None:
    """Pretty-print the vibe match scorecard to stdout."""
    CLR_RESET  = "\033[0m"
    CLR_DIM    = "\033[2m"
    CLR_BOLD   = "\033[1m"

    overall = score["overall"]
    if overall >= 85:
        CLR_GRADE = "\033[1;32m"   # bold green
    elif overall >= 70:
        CLR_GRADE = "\033[1;33m"   # bold yellow
    elif overall >= 55:
        CLR_GRADE = "\033[1;34m"   # bold blue
    else:
        CLR_GRADE = "\033[1;31m"   # bold red

    # Build a 20-char bar
    filled = int(overall / 5)
    bar = "█" * filled + "░" * (20 - filled)

    print(f"\n{CLR_DIM}{'─'*40}{CLR_RESET}")
    print(f"{CLR_BOLD}Vibe Match:{CLR_RESET}  "
          f"{CLR_GRADE}{overall:5.1f}/100  [{bar}]  {score['grade']} — {score['label']}{CLR_RESET}")

    sem_str = (f"{score['semantic']:.1f}" if score["semantic"] is not None
               else "n/a (install sentence-transformers)")
    print(f"{CLR_DIM}  Semantic similarity : {sem_str}{CLR_RESET}")
    print(f"{CLR_DIM}  Length match        : {score['length']:.1f}{CLR_RESET}")
    print(f"{CLR_DIM}  Formality penalty   : {score['formality']:.1f}{CLR_RESET}")
    print(f"{CLR_DIM}  Lexical overlap     : {score['lexical']:.1f}{CLR_RESET}")
    print(f"{CLR_DIM}  (calibrated against your baseline: {score.get('baseline', '?')}){CLR_RESET}")
    print(f"{CLR_DIM}{'─'*40}{CLR_RESET}")

