#!/usr/bin/env python3
"""Enrich playlist.json with title + duration + liveness via yt-dlp.

Politely (1.0–2.5 sec randomized delay between calls). Resumable. Skips
videos that already have `duration` baked in. Dead/blocked videos get
`alive: false` + a `dead_reason`.

Usage:  enrich_playlist.py [--in playlist.json] [--out playlist.json]
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path


def fetch_one(vid: str, timeout: int = 35) -> dict:
    cmd = [
        "yt-dlp",
        "-J", "--skip-download", "--no-warnings", "--no-playlist", "--no-call-home",
        "--socket-timeout", "20",
        "--user-agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "--", f"https://youtu.be/{vid}",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"alive": False, "dead_reason": "timeout"}
    if res.returncode != 0:
        err = (res.stderr or "").strip().splitlines()
        reason = ""
        for line in err[-4:]:
            line = line.strip()
            if "ERROR:" in line:
                reason = line.split("ERROR:", 1)[1].strip()[:200]
                break
        return {"alive": False, "dead_reason": reason or "unknown_error"}
    try:
        info = json.loads(res.stdout or "{}")
    except json.JSONDecodeError:
        return {"alive": False, "dead_reason": "bad_json"}
    return {
        "alive": True,
        "title": info.get("title") or "",
        "duration": info.get("duration"),
        "channel": info.get("uploader") or info.get("channel") or "",
        "channel_id": info.get("channel_id") or info.get("uploader_id") or "",
        "age_limit": info.get("age_limit", 0),
        "is_live": info.get("is_live", False),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=Path("playlist.json"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--min-delay", type=float, default=1.0)
    ap.add_argument("--max-delay", type=float, default=2.5)
    args = ap.parse_args()
    out = args.out or args.inp

    records = json.loads(args.inp.read_text())
    todo = [r for r in records if r.get("duration") is None and r.get("alive") is not False]
    print(f"total: {len(records)}  ·  to enrich: {len(todo)}", flush=True)
    if not todo:
        print("nothing to do.")
        return 0

    alive = dead = 0
    started = time.time()
    for i, rec in enumerate(todo, 1):
        meta = fetch_one(rec["id"])
        if meta.get("alive"):
            alive += 1
            if meta.get("title") and not rec.get("title"):
                rec["title"] = meta["title"]
            rec["duration"] = meta.get("duration")
            rec["channel"] = meta.get("channel", "")
            rec["channel_id"] = meta.get("channel_id", "")
            rec["age_limit"] = meta.get("age_limit", 0)
            rec["is_live"] = meta.get("is_live", False)
            rec["alive"] = True
            status = f"✓ {meta.get('duration') or '?':>5}s  {meta.get('title','')[:50]}"
        else:
            dead += 1
            rec["alive"] = False
            rec["dead_reason"] = meta.get("dead_reason", "")
            status = f"✗ {meta['dead_reason'][:80]}"
        print(f"  [{i:>3}/{len(todo)}] {rec['id']}  {status}", flush=True)
        if i % 10 == 0:
            out.write_text(json.dumps(records, indent=2, ensure_ascii=False))
        time.sleep(random.uniform(args.min_delay, args.max_delay))

    out.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    elapsed = int(time.time() - started)
    print(f"\ndone. alive: {alive}  ·  dead: {dead}  ·  elapsed: {elapsed // 60}m{elapsed % 60}s")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
