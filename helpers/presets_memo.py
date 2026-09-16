from typing import Any

from usr.plugins.runtime_cache.helpers import store

_original: Any = None


def _paths_digest() -> str:
    from helpers import files, plugins
    from plugins._model_config.helpers.model_config import (
        FALLBACK_PRESETS_FILE,
        PRESETS_FILE,
    )

    user_presets = files.get_abs_path(
        files.USER_DIR, files.PLUGINS_DIR, "_model_config", PRESETS_FILE
    )
    plugin_dir = plugins.find_plugin_dir("_model_config")
    fallback_presets = (
        files.get_abs_path(plugin_dir, FALLBACK_PRESETS_FILE) if plugin_dir else ""
    )
    return store.stat_digest((user_presets, fallback_presets))


def install() -> bool:
    global _original
    from plugins._model_config.helpers import model_config

    if _original is not None:
        return True

    original = model_config.get_presets

    def memoized_get_presets(project_name: str | None = None) -> list[Any]:
        if store.plugin_disabled():
            return original(project_name)
        key = (project_name, _paths_digest())
        cached = store.get(store.PRESETS_AREA, key)
        if cached is not None:
            return list(cached)
        result = original(project_name)
        store.put(store.PRESETS_AREA, key, list(result))
        return list(result)

    setattr(model_config, "get_presets", memoized_get_presets)
    _original = original
    return True


def uninstall() -> None:
    global _original
    if _original is None:
        return
    from plugins._model_config.helpers import model_config

    if getattr(model_config.get_presets, "__name__", "") == "memoized_get_presets":
        setattr(model_config, "get_presets", _original)
    _original = None
