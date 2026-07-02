# second-brain-okf-updater

Keep an Obsidian (or any markdown-based second brain) vault automatically
updated from a git-hosted markdown corpus, written as
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
(OKF) v0.1 notes. Single-file, stdlib-only Python 3.10+ tool.

## Structure

```
second-brain-okf-updater/
├── okf_sync.py            # the tool itself (stdlib only)
├── config.example.json    # copy to config.json and edit
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
- `tags` — keyword-rule based (see [Tagging](#tagging) below)
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

## Usage

```bash
cp config.example.json config.json   # edit source_dir / vault_path / tags
python okf_sync.py                   # sync all new/changed notes
python okf_sync.py --dry-run         # preview without writing
python okf_sync.py --force           # overwrite already-synced notes
python okf_sync.py --since 2026-05-01  # only files dated on/after this
python okf_sync.py --config path/to/other-config.json
```

Requires: Python 3.10+, stdlib only.

## License

MIT
