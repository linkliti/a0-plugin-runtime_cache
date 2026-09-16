# Runtime Cache

Caches rendered prompts, system prompt sections, presets, skill listings, secret key listings, and resolved settings with stat-based dependency validation. Warm builds are ~5× faster than stock while file edits stay visible immediately.

## What is cached

- Every `read_prompt_file` render (main prompt, tool prompts, secrets template, project, nested `{{include}}` recursion) – each entry records the stat (mtime_ns + size) of every file it touched
- Tools system fragment (`_11_tools_prompt.build_prompt`), keyed on model identity, tool policy, registered tool kwargs, and file deps
- Skills catalog fragment (`_13_skills_prompt.build_prompt`), keyed on skill-root listings, SKILL.md stat fingerprint, hidden-skill scope, and file deps
- MCP tools fragment (`_12_mcp_prompt.build_prompt`), keyed on MCP server config and file deps
- Model preset resolution (`model_config.get_presets`), stat-keyed
- Skill catalog listing (`helpers.skills.list_skills`), listing-digest keyed
- Secret key listing (`SecretsManager.get_secrets_for_prompt`), stat-keyed on the manager's secrets files – masked keys only, never values
- Resolved settings (`helpers.settings.get_settings`), stat-keyed on `usr/settings.json` + `usr/.env` + `usr/secrets.env`
- Token counts (`helpers.tokens.count_tokens`), content-addressed chunk memo - stable chunks (system prompt, older history) encode once, only new or changed chunks re-encode

## Performance

Benchmarked on machine (Debian/Kali container, `/opt/venv-a0`, median of repeated runs). "Before" is the stock (unpatched) helper; "after" is a warm cache hit through this plugin. Numbers vary by hardware, but ratios hold.

| Cached operation | Strategy | Before (stock) | After (warm hit) | Speedup |
|---|---|---|---|---|
| Main prompt render (nested `{{include}}` chain) | Per-file dependency-stat memoization: each rendered file records the modification time and size of every source file it depends on; a hit re-validates those stats before reusing the render | 94.6 ms cold | 1.4 ms warm | ~70× warm vs cold |
| Tools system fragment | Keyed cache around `build_prompt`: the cache key captures the resolved model identity, tool policy, and registered tool arguments, so the fragment is rebuilt only when any of those actually change | 376.7 ms cold | 0.5 ms warm | ~700× warm vs cold |
| MCP tools fragment | Keyed on the resolved MCP server configuration; rebuilding is skipped entirely while the server list is unchanged | 5.8 ms cold | 0.3 ms warm | ~20× warm vs cold |
| Skills catalog fragment | Keyed on skill-root directory listings plus a stat fingerprint of every `SKILL.md`; the catalog is re-rendered only when skills change on disk | 146.3 ms cold | 6.6 ms warm | ~22× warm vs cold |
| Model preset resolution (`get_presets`) | Stat-keyed memo: preset files feed their `mtime`/`size` into the cache key, so edits invalidate instantly without watchers | 49.9 ms cold | 0.08 ms warm | ~620× warm vs cold |
| Skill listing (`list_skills`) | Listing-digest memo: sorted directory entry names form a cheap digest that detects added or removed skills; returns a fresh copy each hit so callers cannot mutate the cached list | 106.6 ms cold | 2.6 ms warm | ~41× warm vs cold |
| Resolved settings (`get_settings`) | Stat-keyed memo over `settings.json`, `.env`, and `secrets.env`, returning a deep copy per hit so shared state stays safe | 27.7 ms cold | 0.2 ms warm | ~160× warm vs cold |
| Secrets key listing (`get_secrets_for_prompt`) | Stat-keyed memo on the manager's secrets files; stores masked key names only, never credential values | 0.4 ms cold | 0.03 ms warm | ~13× warm vs cold |
| Token counting (`count_tokens`) | Content-addressed chunk memo: text is split at natural boundaries, each chunk is hashed (`SHA-256`), and only chunks never seen before are encoded; stable chunks such as the system prompt are encoded exactly once | 0.8 ms cold (2 KiB) | 0.5 ms warm | grows with text size; large histories re-encode only the newest chunk |
| Full system prompt (all 6 layers) | Combined effect of all strategies above | 310 ms cold / 650 ms stock steady-state | 11.6 ms warm | ~56× vs cold, ~4–8× vs stock per assembled prompt |

Dependency validation adds under 0.25 ms per hit even with 30 recorded file dependencies (roughly 7 µs per stat call), and the disable-check gate on the hot path costs about 5 µs, so cache hits stay effectively free relative to the work they replace.

## Invalidation (automatic, no manual steps, no TTL)

| Change | Mechanism |
|---|---|
| Any prompt/include `.md` edit | Dependency stat check on next lookup (<1 ms) |
| SKILL.md content edit (any skill root) | SKILL.md stat fingerprint watcher (job_loop) → skills areas cleared |
| Model / capability settings change | `usr/settings.json` mtime watcher (job_loop) → full clear |
| Plugin install / uninstall | Plugin directory listing watcher (job_loop) → full clear |
| Preset save | Presets file stat change in key |
| Secret or `.env` credential change | Stat key on the manager's secrets files + `usr/.env` |
| Settings variables change | Stat key on `usr/settings.json` + `usr/.env` + `usr/secrets.env` |
| Context compression | `compact.*` prompt renders trigger a full clear |
| New / removed skill directories | Skill-root listing digest in the skills key |
| Token counts | Content-addressed chunks - pure function of text, no invalidation needed |
| Tool policy or per-tool kwargs change | Included in the tools key |
| MCP server config change | Included in the MCP key |

## Notes

- Cached renders are byte-identical to freshly rendered ones, so provider-side prompt caching (KV cache) stays stable across loops.
- Disabling the plugin stops its hooks but runtime memo patches stay active until framework restart; uninstall restores the originals immediately.
