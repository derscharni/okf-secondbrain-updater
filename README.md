# second-brain-okf-updater

Keep an Obsidian (or any markdown-based second brain) vault automatically
updated from a git-hosted markdown corpus, written as
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
(OKF) v0.1 notes. Single-file, stdlib-only Python 3.10+ tool.

## Structure

```
second-brain-okf-updater/
├── okf_sync.py              # the tool itself (stdlib only, incl. optional LLM client, --watch mode)
├── check_okf_spec.py        # weekly drift check against the upstream OKF spec
├── config.example.json      # copy to config.json and edit
├── scripts/
│   ├── install_cron.sh              # self-service cron installer (batch sync)
│   ├── uninstall_cron.sh            # removes the batch sync cron entry
│   ├── install_spec_check_cron.sh   # self-service cron installer (weekly spec check)
│   └── uninstall_spec_check_cron.sh # removes the spec check cron entry
├── README.md
├── LICENSE                 # MIT
└── .gitignore
```

## What it does

OKF is a minimal, vendor-neutral format for representing knowledge as plain
markdown files with YAML frontmatter — readable by humans without tooling,
parseable by agents without an SDK. This tool takes any folder of markdown
files (a blog, a research vault, a changelog, a wiki export — anything) and
writes OKF-compliant copies into an Obsidian vault, so the notes are
simultaneously useful in Obsidian (Dataview-queryable) *and* consumable by
any OKF-aware tool, agent, or crawler.

Frontmatter written per note:

- `type` — from config, or per-file override
- `title` — first `# ` heading, or filename
- `description` — first real paragraph, truncated to ~240 chars
- `resource` — a stable URI for the source file (raw git URL if the source
  is a git repo with a detected remote, else `file://`)
- `tags` — keyword-rule based, or optionally LLM-assisted (see [Tagging](#tagging)
  and [Optional: LLM-assisted tagging & descriptions](#optional-llm-assisted-tagging--descriptions))
- `timestamp` — ISO 8601, from a `YYYY-MM-DD` filename prefix if present,
  else the file's mtime

Unknown/extra frontmatter in already-synced notes is never touched — this
tool only writes fields it owns, and OKF requires consumers to tolerate and
preserve unrecognized keys, so bring your own extensions freely.

## Tagging

Naive "does this keyword appear anywhere" tagging degrades badly once your
corpus is even lightly topical — every note ends up tagged with almost every
keyword, and filtering by tag stops being useful. The default `top_n` mode
instead *ranks* your configured tags by keyword-hit count per document and
keeps only the top N that clear a minimum hit count — so tags reflect each
note's dominant topics, not just "any topic it briefly touches." Switch to
`any` mode if you'd rather have exhaustive (but noisier) tagging.

## Optional: LLM-assisted tagging & descriptions

By default, tagging is pure keyword-rule based and the description is the
note's first real paragraph — no network calls, no API key needed. You can
optionally delegate tag selection and/or description generation to an LLM
for higher-quality output. This is opt-in and implemented with only
`urllib` from the stdlib — no SDK dependency, no added packages.

Enable it in `config.json`:

```json
"llm": {
  "enabled": true,
  "provider": "anthropic",
  "model": "claude-sonnet-5",
  "api_key_env": "ANTHROPIC_API_KEY",
  "base_url": null,
  "use_for": ["tags", "description"],
  "timeout": 30
}
```

Supported providers:

- **`anthropic`** — set `api_key_env` to the name of an environment variable
  holding your API key (never put the key itself in `config.json`), e.g.
  `export ANTHROPIC_API_KEY=sk-ant-...`
- **`openai`** (or any OpenAI-compatible endpoint) — same idea with
  `OPENAI_API_KEY`; set `base_url` if you're pointing at a compatible
  endpoint other than `api.openai.com`
- **`ollama`** (local LLM, no API key, no data leaves your machine) — run a
  local model (e.g. `ollama run llama3`) and point `base_url` at it
  (default `http://localhost:11434`); set `api_key_env` to `null`

When LLM tagging is enabled, the model only chooses among the tag names
already configured in `tags.keyword_rules` (plus `tags.static`) — it never
invents new tags, so your tag vocabulary stays consistent. If a call fails
(missing key, network error, malformed response) the tool logs a warning
and falls back to the keyword/paragraph method for that note, so a flaky
LLM never breaks a sync run. Pass `--no-llm` to force keyword/paragraph
mode for a single run regardless of what's in `config.json`.

## Watch mode — sync the moment a note is created

Instead of waiting for the next batch run, `--watch` does an initial full
sync and then keeps running, syncing each new or changed `.md` the moment
`fswatch` reports it (same pattern as `membrane/vault_sanitizer.py`):

```bash
python okf_sync.py --watch
```

Requires `fswatch` (`brew install fswatch`). Runs in the foreground — use a
`launchd`/cron-managed process, `tmux`, or similar to keep it alive across
reboots; this project doesn't install a persistent watcher service itself.

## Spec drift check

`okf_sync.py` implements OKF v0.1 as published in
[GoogleCloudPlatform/knowledge-catalog](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) —
a spec that can change upstream. `check_okf_spec.py` checks, once a week,
whether that path has new commits since the last check. It never modifies
`okf_sync.py`'s behavior automatically — it only reports drift so a human
can decide whether the frontmatter fields still match the current spec.

```bash
python3 check_okf_spec.py                    # check now, state in .okf-spec-state.json
python3 check_okf_spec.py --state other.json # use a different state file
```

First run records a baseline silently. Later runs print nothing new unless
the upstream `okf/` path has changed, in which case it prints the old and
new commit SHAs, the latest commit message, and a link to review.

```bash
# weekly, Monday 09:00 by default
./scripts/install_spec_check_cron.sh
SCHEDULE="0 9 * * MON" ./scripts/install_spec_check_cron.sh
./scripts/uninstall_spec_check_cron.sh
```

## Automatic runs via cron

```bash
# default: every 30 minutes, logs to ~/.okf-sync/cron.log
./scripts/install_cron.sh

# customize schedule and/or python binary
SCHEDULE="0 * * * *" PYTHON_BIN=/usr/bin/python3.11 ./scripts/install_cron.sh

# remove it again
./scripts/uninstall_cron.sh
```

The installer is idempotent (safe to re-run to change the schedule) and
only ever touches the single entry it manages, marked with
`# okf-secondbrain-updater` in your crontab — it won't disturb your other
cron jobs. Prefer to set it up yourself? Add a line like this via
`crontab -e`:

```
*/30 * * * * cd /path/to/second-brain-okf-updater && python3 okf_sync.py >> ~/.okf-sync/cron.log 2>&1
```

## Usage

```bash
cp config.example.json config.json   # edit source_dir / vault_path / tags
python okf_sync.py                   # sync all new/changed notes
python okf_sync.py --dry-run         # preview without writing
python okf_sync.py --force           # overwrite already-synced notes
python okf_sync.py --since 2026-05-01  # only files dated on/after this
python okf_sync.py --config path/to/other-config.json
python okf_sync.py --no-llm          # force keyword/paragraph mode, ignore config.json's llm settings
```

Requires: Python 3.10+, stdlib only (LLM calls use `urllib`, no SDK deps).

## License

MIT
