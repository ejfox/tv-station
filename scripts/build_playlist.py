#!/usr/bin/env python3
"""Build a unified YouTube playlist from multiple sources.

Sources (any/all):
  --csv PATH           CSV file with at minimum a `url` column (also reads `title`)
                       Repeatable: --csv a.csv --csv b.csv
  --vault PATH         Path to a directory of .md/.txt files — recursively grepped
                       for YouTube URLs. Notes that contain links are recorded
                       as `sources[].ref`.
  --watch-later PATH   Convenience: same as --csv but documented as such.

Output: ./playlist.json (or --out PATH)

Schema:
  [{ id, title, url, sources: [{kind, ref}] }]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

YT_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/|v/)|youtu\.be/)([a-zA-Z0-9_-]{11})",
    re.IGNORECASE,
)


def ingest_csv(path: Path, kind: str, by_id: dict) -> int:
    n = 0
    with path.open() as f:
        # Sniff for header
        reader = csv.DictReader(f)
        if "url" not in (reader.fieldnames or []):
            f.seek(0)
            reader = csv.reader(f)
            for row in reader:
                for cell in row:
                    m = YT_RE.search(cell or "")
                    if not m: continue
                    vid = m.group(1)
                    rec = by_id.setdefault(vid, {"id": vid, "title": "", "url": f"https://youtu.be/{vid}", "sources": []})
                    rec["sources"].append({"kind": kind, "ref": path.name})
                    n += 1
            return n
        for row in reader:
            url = (row.get("url") or "").strip()
            title = (row.get("title") or "").strip()
            m = YT_RE.search(url)
            if not m: continue
            vid = m.group(1)
            rec = by_id.setdefault(vid, {"id": vid, "title": title, "url": f"https://youtu.be/{vid}", "sources": []})
            if title and not rec["title"]:
                rec["title"] = title
            rec["sources"].append({"kind": kind, "ref": path.name})
            n += 1
    return n


def ingest_vault(root: Path, by_id: dict) -> int:
    n = 0
    md_files = list(root.rglob("*.md")) + list(root.rglob("*.txt"))
    for f in md_files:
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        ids = set(YT_RE.findall(text))
        if not ids: continue
        rel = str(f.relative_to(root))
        for vid in ids:
            rec = by_id.setdefault(vid, {"id": vid, "title": "", "url": f"https://youtu.be/{vid}", "sources": []})
            rec["sources"].append({"kind": "vault", "ref": rel})
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="append", default=[], help="CSV with a `url` column (or any text columns)")
    ap.add_argument("--vault", action="append", default=[], help="Directory of .md/.txt files to grep")
    ap.add_argument("--watch-later", action="append", default=[], help="Same as --csv (cosmetic)")
    ap.add_argument("--out", type=Path, default=Path("playlist.json"))
    args = ap.parse_args()

    by_id: dict[str, dict] = {}

    for p in args.csv:
        n = ingest_csv(Path(p), "csv", by_id)
        print(f"  csv      {p}: {n} URL hits")
    for p in args.watch_later:
        n = ingest_csv(Path(p), "watchlater", by_id)
        print(f"  watch    {p}: {n} URL hits")
    for p in args.vault:
        n = ingest_vault(Path(p), by_id)
        print(f"  vault    {p}: {n} URL hits")

    records = list(by_id.values())
    # de-dupe sources within each record
    for r in records:
        seen = set()
        out = []
        for s in r["sources"]:
            key = (s["kind"], s["ref"])
            if key not in seen:
                seen.add(key); out.append(s)
        r["sources"] = out
    records.sort(key=lambda r: r["id"])

    args.out.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    print(f"\ntotal unique videos: {len(records)}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
