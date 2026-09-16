from typing import Any

from usr.plugins.runtime_cache.helpers import store

_original: Any = None


def install() -> bool:
    global _original
    from helpers import cache, skills as skills_helper

    if _original is not None:
        return True

    original = skills_helper.list_skills

    def memoized_list_skills(
        agent: Any = None,
        include_content: bool = False,
        include_hidden: bool = False,
    ) -> list[Any]:
        if store.plugin_disabled():
            return original(
                agent=agent,
                include_content=include_content,
                include_hidden=include_hidden,
            )
        roots = skills_helper.get_skill_roots(agent)
        try:
            hidden = skills_helper.get_hidden_skills(agent)
            hidden_digest = store.digest(
                [getattr(entry, "name", str(entry)) for entry in hidden]
            )
        except Exception:
            hidden_digest = "unknown"
        key = (
            *cache.determine_cache_key(agent),
            store.listing_digest(roots),
            hidden_digest,
            include_content,
            include_hidden,
        )
        cached = store.get(store.SKILLS_LIST_AREA, key)
        if cached is not None:
            # ponytail: shallow copy - Skill entries shared; safe while callers only read
            return list(cached)
        result = original(
            agent=agent,
            include_content=include_content,
            include_hidden=include_hidden,
        )
        store.put(store.SKILLS_LIST_AREA, key, result)
        return list(result)

    setattr(skills_helper, "list_skills", memoized_list_skills)
    _original = original
    return True


def uninstall() -> None:
    global _original
    if _original is None:
        return
    from helpers import skills as skills_helper

    if getattr(skills_helper.list_skills, "__name__", "") == "memoized_list_skills":
        setattr(skills_helper, "list_skills", _original)
    _original = None
