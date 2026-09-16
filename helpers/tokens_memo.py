import hashlib
import threading
from typing import Any

from usr.plugins.runtime_cache.helpers import store

_original: Any = None
_lock = threading.Lock()
_chunk_counts: dict[str, int] = {}
_full_counts: dict[str, int] = {}
_cleared = False

CHUNK_SIZE = 8192
MAX_CHUNKS = 32768
MAX_FULL = 512


def _split(text: str) -> list[str]:
    # ponytail: hard cut when a window has no newline - chunk sums may drift from a
    # single-pass count for >16KiB no-newline texts. Real prompts contain newlines.
    if len(text) <= CHUNK_SIZE * 2:
        return [text]
    parts: list[str] = []
    start = 0
    n = len(text)
    half = CHUNK_SIZE // 2
    while start < n:
        end = min(start + CHUNK_SIZE, n)
        if end < n:
            cut = text.rfind("\n\n", start + half, end)
            if cut > start:
                end = min(cut + 2, n)
            else:
                cut = text.rfind("\n", start + half, end)
                if cut > start:
                    end = cut + 1
        parts.append(text[start:end])
        start = end
    return parts


def memoized_count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    global _cleared
    if not text:
        return 0
    if store.plugin_disabled():
        if not _cleared:
            with _lock:
                _chunk_counts.clear()
                _full_counts.clear()
            _cleared = True
        return _original(text, encoding_name)
    _cleared = False
    enc = encoding_name.encode("utf-8")
    text_hash = hashlib.sha256(enc + text.encode("utf-8", "replace")).hexdigest()
    with _lock:
        full = _full_counts.get(text_hash)
    if full is not None:
        return full
    total = 0
    for chunk in _split(text):
        chunk_hash = hashlib.sha256(enc + chunk.encode("utf-8", "replace")).hexdigest()
        with _lock:
            count = _chunk_counts.get(chunk_hash)
        if count is None:
            count = _original(chunk, encoding_name)
            with _lock:
                if len(_full_counts) > MAX_FULL:
                    _full_counts.clear()
                if len(_chunk_counts) > MAX_CHUNKS:
                    _chunk_counts.clear()
                _chunk_counts[chunk_hash] = count
        total += count
    with _lock:
        _full_counts[text_hash] = total
    return total


def install() -> bool:
    global _original
    from helpers import tokens

    if _original is not None:
        return True
    _original = tokens.count_tokens
    setattr(tokens, "count_tokens", memoized_count_tokens)
    return True


def uninstall() -> None:
    global _original
    if _original is None:
        return
    from helpers import tokens

    if getattr(tokens.count_tokens, "__name__", "") == "memoized_count_tokens":
        setattr(tokens, "count_tokens", _original)
    _original = None
