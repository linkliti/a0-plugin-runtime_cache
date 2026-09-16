# runtime_cache DOX

## Purpose

- Own the runtime_cache plugin: stat-validated memoization of prompt rendering, model presets, skill listings, tools/MCP prompt fragments, secret key listings, settings resolution, and token counting.

## Ownership

- `plugin.yaml` owns manifest and scope flags.
- `hooks.py` owns lifecycle: installs all memos on install, restores originals on uninstall.
- `helpers/store.py` owns cache areas, key builders, digests, hit/miss counters, and targeted area clearing.
- `helpers/files_memo.py` owns the `read_prompt_file` dependency-stat memo.
- `helpers/skills_memo.py` owns the `list_skills` listing-digest memo.
- `helpers/presets_memo.py` owns the `get_presets` stat-key memo.
- `helpers/env_memo.py` owns the `get_secrets_for_prompt` and `get_settings` stat-key memos.
- `helpers/tokens_memo.py` owns the content-addressed token-count chunk memo.
- `extensions/python/startup_migration/` owns boot-time memo installation.
- `extensions/python/job_loop/_20_watch.py` owns watcher-based invalidation.
- `extensions/python/_functions/` owns tools, MCP, and skills fragment cache hooks.
- `webui/thumbnail.webp` owns the plugin thumbnail.
- `LICENSE` owns the distribution license (MIT).

## Local Contracts

- Every memo monkeypatches inside `install()`: capture the original first, wrap idempotently, restore in `uninstall()` guarded by the wrapper `__name__`.
- Patched modules are imported as module objects (`from helpers import settings`) and patched with `setattr`; never import-and-rebind the function name.
- Secret values are never cached; the secrets memo stores the masked key listing only.
- Invalidation is automatic: dep-stat checks per lookup, stat keys per entry, job_loop watcher for settings/plugins/SKILL.md; no TTL and no manual reload path.
- `compact.*` renders clear all areas; SKILL.md fingerprint changes clear only the skills areas.
- No top-file docstrings and no `# type:` / `# pyright:` meta comments.
- Every memo and fragment hook checks `store.plugin_disabled()` first and passes through to the original when disabled; a fresh disable clears cached state live.
- Token-count chunks are content-addressed and never stale; a fresh disable clears the count tables.
- Known limitation: the monkeypatch layer is process-wide; framework per-project/per-agent plugin toggles stop this plugin's extensions for that scope but the patched helpers keep memoizing until the root-level toggle disables it.
- Settings and secrets stat keys resolve through `files.get_abs_path` so digests never depend on process CWD.

## Work Guidance

- Keep cached output byte-identical to fresh renders so provider KV-cache prefixes stay stable.
- Keep per-loop overhead bounded: key builders stay stat/digest-based, watcher work stays lister-level, never file-content reads.

## Verification

- From `/a0/usr/plugins` with `/opt/venv-a0`: `python -m basedpyright runtime_cache` reports 0 errors, `python -m ruff check runtime_cache` and `python -m ruff format --check runtime_cache` pass.
- From `/a0`: `/opt/venv-a0/bin/python /a0/usr/projects/plugin_dev/bench_prompt_cache.py` reports `ident` on every cached row; `/opt/venv-a0/bin/python /a0/usr/projects/plugin_dev/bench_prepare_prompt.py` shows warm << cold.

## Child DOX Index

No child DOX files.
