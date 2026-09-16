import copy
from typing import Any

from usr.plugins.runtime_cache.helpers import store

_secrets_original: Any = None
_settings_original: Any = None


def install() -> bool:
    global _secrets_original, _settings_original
    from helpers import dotenv, files, settings
    from helpers.secrets import DEFAULT_SECRETS_FILE, SecretsManager

    if _secrets_original is None:
        original = SecretsManager.get_secrets_for_prompt

        def memoized_get_secrets_for_prompt(self: Any) -> str:
            if store.plugin_disabled():
                return original(self)
            # framework reads these via files.read_file (basedir-relative) -
            # resolve the same way so stats match regardless of process CWD
            manager_files = tuple(
                files.get_abs_path(p) for p in getattr(self, "_files", ()) or ()
            )
            key = (store.stat_digest(manager_files),)
            cached = store.get(store.SECRETS_AREA, key)
            if cached is not None:
                return cached
            result = original(self)
            store.put(store.SECRETS_AREA, key, result)
            return result

        setattr(
            SecretsManager, "get_secrets_for_prompt", memoized_get_secrets_for_prompt
        )
        _secrets_original = original

    if _settings_original is None:
        original_settings = settings.get_settings

        def memoized_get_settings() -> Any:
            if store.plugin_disabled():
                return original_settings()
            key = (
                store.stat_digest(
                    (
                        settings.SETTINGS_FILE,
                        dotenv.get_dotenv_file_path(),
                        files.get_abs_path(DEFAULT_SECRETS_FILE),
                    )
                ),
            )
            cached = store.get(store.SETTINGS_AREA, key)
            if cached is not None:
                return copy.deepcopy(cached)
            result = original_settings()
            store.put(store.SETTINGS_AREA, key, copy.deepcopy(result))
            return result

        setattr(settings, "get_settings", memoized_get_settings)
        _settings_original = original_settings

    return True


def uninstall() -> None:
    global _secrets_original, _settings_original
    from helpers import settings
    from helpers.secrets import SecretsManager

    if _secrets_original is not None:
        if (
            getattr(SecretsManager.get_secrets_for_prompt, "__name__", "")
            == "memoized_get_secrets_for_prompt"
        ):
            setattr(SecretsManager, "get_secrets_for_prompt", _secrets_original)
        _secrets_original = None

    if _settings_original is not None:
        if getattr(settings.get_settings, "__name__", "") == "memoized_get_settings":
            setattr(settings, "get_settings", _settings_original)
        _settings_original = None
