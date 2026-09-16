import contextvars
import os
from typing import Any

from usr.plugins.runtime_cache.helpers import store

_original: Any = None

# render stack: outermost frame collects every file stat touched by nested reads
_frame: contextvars.ContextVar[dict[str, tuple[int, int]] | None] = (
    contextvars.ContextVar("runtime_cache_file_deps", default=None)
)


def _deps_valid(deps: dict[str, tuple[int, int]]) -> bool:
    for path, (mtime_ns, size) in deps.items():
        try:
            st = os.stat(path)
        except OSError:
            return False
        if st.st_mtime_ns != mtime_ns or st.st_size != size:
            return False
    return True


def dep_get(area: str, key: tuple[Any, ...]) -> Any | None:
    """Return cached result whose recorded file deps all still match, else None."""
    cached = store.get(area, key)
    if cached is not None:
        if _deps_valid(cached[1]):
            return cached[0]
        store.recount_miss()
    return None


def dep_capture_start() -> None:
    """Begin collecting file deps for an outer (fragment-level) render."""
    _frame.set({})


def dep_capture_end(area: str, key: tuple[Any, ...], result: Any) -> None:
    """Store an outer render result with the deps collected since capture_start."""
    frame = _frame.get()
    if frame is not None:
        store.put(area, key, (result, dict(frame)))


def install() -> bool:
    global _original
    from helpers import files

    if _original is not None:
        return True

    original = files.read_prompt_file

    def memoized_read_prompt_file(
        _file: str,
        _directories: list[str] | None = None,
        _encoding: str = "utf-8",
        **kwargs: Any,
    ) -> Any:
        if (
            store.plugin_disabled()
            or not store.cacheable_kwargs(kwargs)
            or any(str(_file).startswith(prefix) for prefix in store.DYNAMIC_FILES)
        ):
            return original(_file, _directories, _encoding, **kwargs)

        try:
            # mirror the framework's resolution exactly: dirname extracted first,
            # then find_file_in_dirs over [folder] + directories (see files.py)
            directories = list(_directories or [])
            file_name = str(_file)
            if os.path.dirname(file_name):
                directories = [os.path.dirname(file_name)] + directories
                file_name = os.path.basename(file_name)
            absolute_path = files.find_file_in_dirs(file_name, directories)
            st = os.stat(absolute_path)
            key = (
                absolute_path,
                str(_file),
                tuple(str(d) for d in (_directories or ())),
                _encoding,
                store.digest(kwargs),
            )
        except Exception:
            return original(_file, _directories, _encoding, **kwargs)

        parent_frame = _frame.get()
        if parent_frame is not None:
            parent_frame[absolute_path] = (st.st_mtime_ns, st.st_size)

        cached = store.get(store.RP_AREA, key)
        if cached is not None and _deps_valid(cached[1]):
            return cached[0]

        frame: dict[str, tuple[int, int]] = {}
        token = _frame.set(frame)
        try:
            result = original(_file, _directories, _encoding, **kwargs)
        finally:
            _frame.reset(token)

        if str(_file).startswith("compact."):
            # context compression rerenders compact.* prompts - unfreeze everything after
            store.clear_all()
            return result

        deps = dict(frame)
        deps[absolute_path] = (st.st_mtime_ns, st.st_size)
        store.put(store.RP_AREA, key, (result, deps))
        return result

    setattr(files, "read_prompt_file", memoized_read_prompt_file)
    _original = original
    return True


def uninstall() -> None:
    global _original
    if _original is None:
        return
    from helpers import files

    if getattr(files.read_prompt_file, "__name__", "") == "memoized_read_prompt_file":
        setattr(files, "read_prompt_file", _original)
    _original = None
