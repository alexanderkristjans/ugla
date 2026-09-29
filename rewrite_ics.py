#!/usr/bin/env python3
"""
Fetch an .ics calendar, rewrite event text fields according to rules.toml,
and write the result to public/calendar.ics.

No third-party dependencies (Python 3.11+). The file is edited line by line,
so everything the rules don't touch (UIDs, time zones, alarms, recurrence,
attendees, vendor extensions) passes through unchanged.

Usage:
    ICS_URL="https://..." python rewrite_ics.py
    python rewrite_ics.py --input local.ics --output out.ics   # for testing
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


# ---------- iCalendar text helpers (RFC 5545) ----------

def unfold(text: str) -> list[str]:
    """Join folded continuation lines (lines starting with a space or tab)."""
    lines: list[str] = []
    for raw in re.split(r"\r\n|\n|\r", text):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def fold(line: str, limit: int = 75) -> str:
    """Fold a content line at <=75 octets without splitting UTF-8 characters."""
    out, current, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        max_size = limit if not out else limit - 1  # continuation lines start with a space
        if size + n > max_size:
            out.append(current)
            current, size = ch, n
        else:
            current += ch
            size += n
    out.append(current)
    return "\r\n ".join(out)


def split_property(line: str) -> tuple[str, str, str] | None:
    """Split 'NAME;PARAM="a:b":value' into (name, params, value)."""
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ":" and not in_quotes:
            head, value = line[:i], line[i + 1:]
            name, _, params = head.partition(";")
            return name.upper(), (";" + params if params else ""), value
    return None


def unescape(value: str) -> str:
    return re.sub(r"\\([\\;,nN])",
                  lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def escape(value: str) -> str:
    return (value.replace("\\", "\\\\").replace(";", "\\;")
                 .replace(",", "\\,").replace("\n", "\\n"))


# ---------- rules ----------

def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    rules = []
    for r in cfg.get("rule", []):
        fields = r.get("fields", ["SUMMARY"])
        if isinstance(fields, str):
            fields = [fields]
        flags = re.IGNORECASE if r.get("ignore_case", False) else 0
        pattern = r["find"] if r.get("regex", False) else re.escape(r["find"])
        rules.append({
            "fields": {f.upper() for f in fields},
            "pattern": re.compile(pattern, flags),
            "replace": r.get("replace", ""),
            "regex": r.get("regex", False),
        })
    cfg["_rules"] = rules
    return cfg


def apply_rules(field: str, value: str, rules: list[dict]) -> str:
    original = value
    for r in rules:
        if field in r["fields"]:
            repl = r["replace"] if r["regex"] else r["replace"].replace("\\", "\\\\")
            value = r["pattern"].sub(repl, value)
    if value != original:  # tidy up spaces left behind by removals
        value = re.sub(r"[ \t]{2,}", " ", value).strip()
    return value


def transform(text: str, cfg: dict) -> tuple[str, int]:
    rules = cfg["_rules"]
    cal_name = cfg.get("calendar_name")
    out: list[str] = []
    in_event = False
    changed = 0
    saw_calname = False

    for line in unfold(text):
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            in_event = True
        elif upper == "END:VEVENT":
            in_event = False

        parts = split_property(line)
        if parts:
            name, params, value = parts

            if not in_event and name == "X-WR-CALNAME" and cal_name:
                saw_calname = True
                line = f"X-WR-CALNAME{params}:{escape(cal_name)}"

            elif in_event and any(name in r["fields"] for r in rules):
                new = apply_rules(name, unescape(value), rules)
                if new != unescape(value):
                    changed += 1
                    line = f"{name}{params}:{escape(new)}"

        out.append(line)

    # Add a calendar name if the source has none
    if cal_name and not saw_calname:
        idx = next((i for i, l in enumerate(out) if l.upper() == "BEGIN:VCALENDAR"), None)
        if idx is not None:
            out.insert(idx + 1, f"X-WR-CALNAME:{escape(cal_name)}")

    return "\r\n".join(fold(l) for l in out) + "\r\n", changed


# ---------- main ----------

def fetch(url: str) -> str:
    url = re.sub(r"^webcal://", "https://", url, flags=re.IGNORECASE)
    req = urllib.request.Request(url, headers={"User-Agent": "ics-rewriter/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    text = data.decode("utf-8-sig", errors="replace")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise SystemExit("Downloaded content is not an iCalendar file — check ICS_URL.")
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="Read a local .ics instead of fetching ICS_URL")
    ap.add_argument("--output", default=str(HERE / "public" / "calendar.ics"))
    ap.add_argument("--config", default=str(HERE / "rules.toml"))
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8-sig")
    else:
        url = os.environ.get("ICS_URL") or cfg.get("source_url")
        if not url:
            sys.exit("Set the ICS_URL environment variable (or source_url in rules.toml).")
        text = fetch(url)

    result, changed = transform(text, cfg)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result, encoding="utf-8", newline="")
    events = result.upper().count("BEGIN:VEVENT")
    print(f"Wrote {out} — {events} events, {changed} fields rewritten.")


if __name__ == "__main__":
    main()
