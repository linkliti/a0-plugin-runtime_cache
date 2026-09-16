import os
from pathlib import Path
from typing import Any, override

from helpers.extension import Extension
from helpers import files, settings
from usr.plugins.runtime_cache.helpers import store


def _settings_mtime() -> str:
    try:
        return str(os.stat(settings.SETTINGS_FILE).st_mtime_ns)
    except OSError:
        return ""


def _skills_fingerprint() -> str:
    """Stat fingerprint of every SKILL.md under every global skill root."""
    import hashlib

    from helpers import skills as skills_helper

    h = hashlib.sha256()
    for root in skills_helper.get_skill_roots(None):
        try:
            entries = sorted(Path(root).rglob("SKILL.md"))
        except OSError:
            continue
        for path in entries:
            try:
                st = path.stat()
            except OSError:
                continue
            h.update(f"{path}:{st.st_mtime_ns}:{st.st_size}".encode("utf-8", "replace"))
    return h.hexdigest()[:16]


class Watch(Extension):
    @override
    def execute(self, **kwargs: Any) -> None:
        state = {
            "settings": _settings_mtime(),
            "plugins": store.listing_digest(
                ["/a0/plugins", files.get_abs_path("usr/plugins")]
            ),
            "skills": _skills_fingerprint(),
        }
        previous = store.watch_state()
        if previous:
            if previous.get("settings") != state["settings"]:
                store.clear_all()
            else:
                if previous.get("plugins") != state["plugins"]:
                    store.clear_all()
                if previous.get("skills") != state["skills"]:
                    store.clear_areas((store.SKILLS_AREA, store.SKILLS_LIST_AREA))
        store.set_watch_state(state)
