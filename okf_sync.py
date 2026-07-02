#!/usr/bin/env python3
"""second-brain-okf-updater — keep an Obsidian (or any markdown-based second
brain) vault automatically updated from a git-hosted markdown corpus,
written as Open Knowledge Format (OKF) v0.1 notes.

OKF (github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) is a
minimal, vendor-neutral format for representing knowledge as plain markdown
files with YAML frontmatter — readable by humans without tooling, parseable
by agents without an SDK. This tool takes any folder of markdown files (a
blog, a research vault, a changelog, a wiki export — anything) and writes
OKF-compliant copies into an Obsidian vault, so the notes are simultaneously
useful in Obsidian (Dataview-queryable) *and* consumable by any OKF-aware
tool, agent, or crawler.

Frontmatter written per note:
    type:        from config, or per-file override
    title:       first "# " heading, or filename
    description: first real paragraph, truncated to ~240 chars
    resource:    a stable URI for the source file (raw git URL if the
                 source is a git repo with a detected remote, else file://)
    tags:        keyword-rule based (see "Tagging" below)
    timestamp:   ISO 8601 — from a YYYY-MM-DD filename prefix if present,
                 else the file's mtime

Unknown/extra frontmatter in already-synced notes is never touched — this
tool only writes fields it owns, and OKF requires consumers to tolerate and
preserve unrecognized keys, so bring your own extensions freely.

Tagging
-------
Naive "does this keyword appear anywhere" tagging degrades badly once your
corpus is even lightly topical — every note ends up tagged with almost every
keyword, and filtering by tag stops being useful (this is exactly the bug
that motivated writing this tool: see the "tag_rules" section in
config.example.json). The default `top_n` mode instead *ranks* your
configured tags by keyword-hit count per document and keeps only the
top N that clear a minimum hit count — so tags reflect each note's
dominant topics, not just "any topic it briefly touches." Switch to `any`
mode if you'd rather have exhaustive (but noisier) tagging.

Usage
-----
    cp config.example.json config.json   # edit source_dir / vault_path / tags
    python okf_sync.py                   # sync all new/changed notes
    python okf_sync.py --dry-run         # preview without writing
    python okf_sync.py --force           # overwrite already-synced notes
    python okf_sync.py --since 2026-05-01  # only files dated on/after this
    python okf_sync.py --config path/to/other-config.json

Requires: Python 3.10+, stdlib only.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"

DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


# ── Config ───────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(
            f"Config file not found: {path}\n"
            f"Copy config.example.json to config.json and edit source_dir / vault_path."
        )
    cfg = json.loads(path.read_text())
    for required in ("source_dir", "vault_path"):
        if not cfg.get(required):
            sys.exit(f"config.json is missing required field: {required}")
    cfg.setdefault("dest_folder", "OKF Sync")
    cfg.setdefault("file_glob", "**/*.md")
    cfg.setdefault("type_field", "Note")
    cfg.setdefault("title_pattern", r"^#\s+(.+)$")
    cfg.setdefault("resource_base_url", None)
    cfg.setdefault("tags", {})
    cfg["tags"].setdefault("static", [])
    cfg["tags"].setdefault("keyword_rules", {})
    cfg["tags"].setdefault("mode", "top_n")   # "top_n" or "any"
    cfg["tags"].setdefault("top_n", 2)
    cfg["tags"].setdefault("min_hits", 2)
    return cfg


# ── Extraction ───────────────────────────────────────────────────────────────

def strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            return content[end + 4:]
    return content


def extract_title(content: str, pattern: str, fallback: str) -> str:
    m = re.search(pattern, content, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def strip_md(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\[(\d+)\]", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`#]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_description(body: str, max_len: int = 240) -> str:
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("---"):
            continue
        if re.fullmatch(r"\*\*.+\*\*", s):
            continue
        d = strip_md(s)
        if len(d) > 20:
            return d[:max_len]
    return ""


def detect_tags(content: str, tags_cfg: dict) -> list[str]:
    lower = content.lower()
    rules: dict[str, list[str]] = tags_cfg["keyword_rules"]
    scores = {tag: sum(lower.count(kw.lower()) for kw in kws) for tag, kws in rules.items()}
    scores = {t: c for t, c in scores.items() if c > 0}

    if tags_cfg["mode"] == "any":
        matched = list(scores.keys())
    else:  # top_n
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[: tags_cfg["top_n"]]
        matched = [t for t, c in ranked if c >= tags_cfg["min_hits"]]

    return list(tags_cfg["static"]) + matched


def detect_timestamp(path: Path) -> str:
    m = DATE_PREFIX_RE.match(path.stem)
    if m:
        return f"{m.group(1)}T00:00:00Z"
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return mtime.strftime("%Y-%m-%dT%H:%M:%SZ")


def detect_date_for_filter(path: Path) -> str | None:
    m = DATE_PREFIX_RE.match(path.stem)
    if m:
        return m.group(1)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return mtime.strftime("%Y-%m-%d")


# ── Resource URL ────────────────────────────────────────────────────────────

def detect_git_raw_base(source_dir: Path) -> str | None:
    """Best-effort: turn a GitHub `origin` remote into a raw.githubusercontent.com base."""
    try:
        remote = subprocess.run(
            ["git", "-C", str(source_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(source_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return None

    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
    if not m:
        return None
    return f"https://raw.githubusercontent.com/{m.group(1)}/{branch}"


def resolve_resource_url(path: Path, source_dir: Path, raw_base: str | None) -> str:
    rel = path.relative_to(source_dir).as_posix()
    if raw_base:
        return f"{raw_base}/{rel}"
    return path.resolve().as_uri()


# ── Frontmatter ──────────────────────────────────────────────────────────────

def yaml_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_note(path: Path, cfg: dict, raw_base: str | None) -> str:
    content = path.read_text(encoding="utf-8")
    body = strip_frontmatter(content)

    title = extract_title(body, cfg["title_pattern"], path.stem)
    description = extract_description(body)
    resource = resolve_resource_url(path, Path(cfg["source_dir"]), raw_base)
    tags = detect_tags(body, cfg["tags"])
    timestamp = detect_timestamp(path)

    lines = [
        "---",
        f"type: {cfg['type_field']}",
        f'title: "{yaml_escape(title)}"',
    ]
    if description:
        lines.append(f'description: "{yaml_escape(description)}"')
    lines.append(f"resource: {resource}")
    if tags:
        lines.append("tags:")
        lines += [f"  - {t}" for t in tags]
    lines.append(f"timestamp: {timestamp}")
    lines += ["---", ""]

    return "\n".join(lines) + body


# ── Sync ─────────────────────────────────────────────────────────────────────

def sync(cfg: dict, dry_run: bool, force: bool, since: str | None) -> None:
    source_dir = Path(cfg["source_dir"]).expanduser().resolve()
    vault_dest = Path(cfg["vault_path"]).expanduser() / cfg["dest_folder"]
    raw_base = cfg["resource_base_url"] or detect_git_raw_base(source_dir)

    if not source_dir.is_dir():
        sys.exit(f"source_dir does not exist: {source_dir}")

    files = sorted(source_dir.glob(cfg["file_glob"]))
    if since:
        files = [f for f in files if (detect_date_for_filter(f) or "") >= since]

    if dry_run:
        print(f"[DRY RUN] source={source_dir}  dest={vault_dest}")
    if raw_base:
        print(f"resource base URL: {raw_base}")
    else:
        print("resource base URL: none detected — using file:// URIs")

    counts = {"created": 0, "updated": 0, "skipped": 0, "dry": 0}
    for path in files:
        dest = vault_dest / path.relative_to(source_dir)
        if dest.exists() and not force and not dry_run:
            counts["skipped"] += 1
            continue

        note = build_note(path, cfg, raw_base)
        if dry_run:
            counts["dry"] += 1
            print(f"\n{'─'*60}\nPREVIEW: {path.relative_to(source_dir)}\n{'─'*60}")
            print(note[: note.index("---", 4) + 3])
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            existed = dest.exists()
            dest.write_text(note, encoding="utf-8")
            counts["updated" if existed else "created"] += 1
            print(f"  [{'updated' if existed else 'created':7s}] {path.relative_to(source_dir)}")

    total = counts["created"] + counts["updated"] + counts["dry"]
    print(f"\n{'─'*40}\n  synced  : {total}\n  skipped : {counts['skipped']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--since", help="Only sync files dated on/after YYYY-MM-DD")
    args = parser.parse_args()

    cfg = load_config(args.config)
    sync(cfg, dry_run=args.dry_run, force=args.force, since=args.since)


if __name__ == "__main__":
    main()
