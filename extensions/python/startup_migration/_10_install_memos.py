from typing import Any, override

from helpers.extension import Extension
from usr.plugins.runtime_cache.helpers import (
    env_memo,
    files_memo,
    presets_memo,
    skills_memo,
    tokens_memo,
)


class InstallMemos(Extension):
    @override
    def execute(self, **kwargs: Any) -> None:
        files_memo.install()
        skills_memo.install()
        presets_memo.install()
        env_memo.install()
        tokens_memo.install()
