from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any

from helpers import cache

RP_AREA = "runtime_cache(read_prompt)"
TOOLS_AREA = "runtime_cache(tools)"
SKILLS_AREA = "runtime_cache(skills)"
MCP_AREA = "runtime_cache(mcp)"
SKILLS_LIST_AREA = "runtime_cache(skills_list)"
PRESETS_AREA = "runtime_cache(presets)"
SECRETS_AREA = "runtime_cache(secrets)"
SETTINGS_AREA = "runtime_cache(settings)"
AREAS = (
    RP_AREA,
    TOOLS_AREA,
    SKILLS_AREA,
    MCP_AREA,
    SKILLS_LIST_AREA,
    PRESETS_AREA,
    SECRETS_AREA,
    SETTINGS_AREA,
)

# ponytail: coarse leak cap - drop a whole area after too many distinct keys
MAX_KEYS_PER_AREA = 1024

# kwargs values above this size are treated as uncacheable (compaction conversations)
MAX_KWARG_CHARS = 256_000

# prompts that embed per-call dynamic values - caching them is pure key churn
DYNAMIC_FILES = ("agent.system.datetime.",)

_lock = threading.Lock()
_counts: dict[str, int] = dict.fromkeys(AREAS, 0)
_counters: dict[str, int] = {"hits": 0, "misses": 0}
_watch: dict[str, str] = {}


def digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def listing_digest(roots: list[str]) -> str:
    """Digest of sorted root-directory entry names (OSError dirs count empty)."""
    h = hashlib.sha256()
    for root in roots:
        try:
            names = sorted(entry.name for entry in os.scandir(root))
        except OSError:
            names = []
        h.update(("\n".join(names)).encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def stat_digest(paths: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    for path in paths:
        try:
            st = os.stat(path)
            h.update(f"{path}:{st.st_mtime_ns}:{st.st_size}".encode())
        except OSError:
            h.update(f"{path}:missing".encode())
    return h.hexdigest()[:16]


def cacheable_kwargs(kwargs: dict[str, Any]) -> bool:
    return not any(
        isinstance(value, str) and len(value) > MAX_KWARG_CHARS
        for value in kwargs.values()
    )


def get(area: str, key: tuple[Any, ...]) -> Any:
    value = cache.get(area, key)
    with _lock:
        if value is None:
            _counters["misses"] += 1
        else:
            _counters["hits"] += 1
    return value


def put(area: str, key: tuple[Any, ...], value: Any) -> None:
    cache.add(area, key, value)
    with _lock:
        _counts[area] = _counts.get(area, 0) + 1
        if _counts[area] > MAX_KEYS_PER_AREA:
            _counts[area] = 0
            cache.clear(area)


def clear_all() -> dict[str, int]:
    global _counts
    with _lock:
        stats = dict(_counters)
        _counters["hits"] = 0
        _counters["misses"] = 0
        _counts = dict.fromkeys(AREAS, 0)
    for area in AREAS:
        cache.clear(area)
    return stats


def clear_areas(areas: tuple[str, ...]) -> None:
    """Clear selected cache areas and their key counters (targeted invalidation)."""
    with _lock:
        for area in areas:
            if area in _counts:
                _counts[area] = 0
    for area in areas:
        cache.clear(area)


def stats() -> dict[str, int]:
    with _lock:
        return dict(_counters)


def recount_miss() -> None:
    """Recount a dep-invalidated entry as a miss (hit was already counted)."""
    with _lock:
        _counters["hits"] -= 1
        _counters["misses"] += 1


def watch_state() -> dict[str, str]:
    with _lock:
        return dict(_watch)


def set_watch_state(state: dict[str, str]) -> None:
    with _lock:
        _watch.clear()
        _watch.update(state)


_DISABLE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".toggle-0"
)
_disabled = False


def plugin_disabled() -> bool:
    global _disabled
    disabled = os.path.exists(_DISABLE_FILE)
    if disabled and not _disabled:
        clear_all()
    _disabled = disabled
    return disabled


def _scope(agent: Any) -> tuple[Any, ...]:
    try:
        return cache.determine_cache_key(agent)
    except Exception:
        return ("none", "none")


def _model_identity(agent: Any) -> str:
    try:
        from plugins._model_config.helpers.model_config import (
            get_chat_model_config,
            get_vision_model_config,
        )

        chat = get_chat_model_config(agent)
        vision = bool(get_vision_model_config(agent))
        return f"{chat.get('provider', '')}:{chat.get('name', '')}:vision={vision}"
    except Exception:
        return "unknown"


def _policy_digest(agent: Any) -> str:
    try:
        from helpers import tool_policy

        return digest(tool_policy.get_policy(agent))
    except Exception:
        return "unknown"


def tools_key(agent: Any) -> tuple[Any, ...] | None:
    """Key for the tools system fragment: scope, model, policy, kwargs, prompt dirs."""
    try:
        from extensions.python.system_prompt._11_tools_prompt import TOOL_KWARGS_KEY
        from helpers import subagents

        tool_kwargs = agent.get_data(TOOL_KWARGS_KEY) if agent else None
        override = None
        try:
            override = agent.context.get_data("chat_model_override")
        except Exception:
            override = None
        prompt_dirs = subagents.get_paths(agent, "prompts", must_exist_completely=False)
        return (
            *_scope(agent),
            digest(override or {}),
            _model_identity(agent),
            _policy_digest(agent),
            digest(tool_kwargs or {}),
            listing_digest(prompt_dirs),
        )
    except Exception:
        return None


def skills_key(agent: Any) -> tuple[Any, ...] | None:
    """Key for the skills catalog fragment: root listings, hidden scope, policy."""
    try:
        from helpers import skills as skills_helper

        roots = skills_helper.get_skill_roots(agent)
        hidden = skills_helper.get_hidden_skills(agent)
        hidden_digest = digest([getattr(entry, "name", str(entry)) for entry in hidden])
        return (
            *_scope(agent),
            listing_digest(roots),
            hidden_digest,
            _policy_digest(agent),
        )
    except Exception:
        return None


def mcp_key(agent: Any) -> tuple[Any, ...] | None:
    """Key for the MCP tools fragment: server config, live tool lists, policy."""
    try:
        from helpers.mcp_handler import MCPConfig

        config = MCPConfig.get_for_agent(agent)
        tool_lists: list[Any] = []
        for server in config.servers:
            try:
                tool_lists.append([str(t.get("name", "")) for t in server.get_tools()])
            except Exception:
                tool_lists.append(None)
        return (
            *_scope(agent),
            digest([repr(s) for s in config.servers]),
            digest(tool_lists),
            _policy_digest(agent),
        )
    except Exception:
        return None
