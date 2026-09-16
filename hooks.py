from usr.plugins.runtime_cache.helpers import (
    env_memo,
    files_memo,
    presets_memo,
    skills_memo,
    tokens_memo,
)


def install() -> None:
    files_memo.install()
    skills_memo.install()
    presets_memo.install()
    env_memo.install()
    tokens_memo.install()


def uninstall() -> None:
    tokens_memo.uninstall()
    env_memo.uninstall()
    files_memo.uninstall()
    skills_memo.uninstall()
    presets_memo.uninstall()
