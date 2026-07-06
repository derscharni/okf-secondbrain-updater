#!/usr/bin/env python3
"""check_okf_spec.py — weekly drift check against the official OKF spec.

okf_sync.py implements Open Knowledge Format (OKF) v0.1
(github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf), a spec
that can itself change upstream. This script checks, once a week, whether
the upstream okf/ path has new commits since the last check — it does not
change any local behavior, it only reports drift so a human can decide
whether okf_sync.py needs updating.

Stdlib only (urllib), no dependencies, no auth required for the public
GitHub API's low-volume anonymous rate limit (60 req/hour is plenty for a
weekly check).

Usage:
    python3 check_okf_spec.py              # check and report
    python3 check_okf_spec.py --state path/to/state.json
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SPEC_OWNER = "GoogleCloudPlatform"
SPEC_REPO = "knowledge-catalog"
SPEC_PATH = "okf"
API_URL = (
    f"https://api.github.com/repos/{SPEC_OWNER}/{SPEC_REPO}"
    f"/commits?path={SPEC_PATH}&per_page=1"
)
DEFAULT_STATE_PATH = Path(__file__).parent / ".okf-spec-state.json"


def fetch_latest_commit():
    req = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "okf-secondbrain-updater/check_okf_spec",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data:
        return None
    commit = data[0]
    return {
        "sha": commit["sha"],
        "date": commit["commit"]["committer"]["date"],
        "message": commit["commit"]["message"].splitlines()[0],
        "html_url": commit["html_url"],
    }


def load_state(path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_state(path, latest):
    path.write_text(json.dumps(latest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    args = parser.parse_args()

    try:
        latest = fetch_latest_commit()
    except urllib.error.HTTPError as e:
        print(f"[check_okf_spec] GitHub API error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[check_okf_spec] network error: {e.reason}", file=sys.stderr)
        sys.exit(1)

    if latest is None:
        print("[check_okf_spec] no commits found for okf/ — unexpected, check the path")
        sys.exit(1)

    previous = load_state(args.state)

    if previous is None:
        print(f"[check_okf_spec] first run — recording baseline: {latest['sha'][:12]} ({latest['date']})")
        save_state(args.state, latest)
        sys.exit(0)

    if previous["sha"] == latest["sha"]:
        print(f"[check_okf_spec] no change since {previous['date']} ({previous['sha'][:12]})")
        sys.exit(0)

    print(
        "[check_okf_spec] OKF SPEC UPDATED\n"
        f"  previous: {previous['sha'][:12]} ({previous['date']})\n"
        f"  latest:   {latest['sha'][:12]} ({latest['date']}) — {latest['message']}\n"
        f"  {latest['html_url']}\n"
        "  Review whether okf_sync.py's frontmatter fields still match the spec."
    )
    save_state(args.state, latest)
    sys.exit(0)


if __name__ == "__main__":
    main()
