from typing import Any, override

from helpers.extension import Extension

from usr.plugins.runtime_cache.helpers import files_memo


class CacheSkillsEnd(Extension):
    @override
    def execute(self, data: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if not data:
            return
        recorded = data.pop("_pck", None)
        if data.get("exception") is not None:
            return
        result = data.get("result")
        if recorded and result is not None:
            files_memo.dep_capture_end(recorded[0], recorded[1], result)
