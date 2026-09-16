from typing import Any, override

from helpers.extension import Extension

from usr.plugins.runtime_cache.helpers import files_memo, store


class CacheSkillsStart(Extension):
    @override
    def execute(self, data: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if not data or store.plugin_disabled():
            return
        key = store.skills_key(self.agent)
        if key is None:
            return
        cached = files_memo.dep_get(store.SKILLS_AREA, key)
        if cached is not None:
            data["result"] = cached
            return
        files_memo.dep_capture_start()
        data["_pck"] = (store.SKILLS_AREA, key)
