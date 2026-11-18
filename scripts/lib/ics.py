#!/usr/bin/env python3
"""导出层：iCalendar (.ics)，让计划直接进系统日历/手机日历。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .cal import parse_date


def _fold(line: str) -> str:
    """RFC 5545 规定每行不超过 75 字节，超长需折行。"""
    raw = line.encode("utf-8")
    if len(raw) <= 73:
        return line
    out, buf = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(buf) + len(b) > 71:
            out.append(buf.decode("utf-8"))
            buf = b
        else:
            buf += b
    out.append(buf.decode("utf-8"))
    return "\r\n ".join(out)


def _esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(plan: dict[str, Any], latest_logs: dict[str, dict] | None = None,
           only_pending: bool = False) -> str:
    latest_logs = latest_logs or {}
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//life-mentor//plan export//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(plan.get('goal', '人生导师计划'))}",
    ]

    for entry in plan.get("days", []):
        d = parse_date(entry["date"])
        log = latest_logs.get(entry["date"], {})
        done_ids = set(log.get("done_tasks", []))
        tasks = entry.get("tasks", [])
        if only_pending:
            tasks = [t for t in tasks if t.get("id") not in done_ids]
        for i, task in enumerate(tasks):
            start_dt = datetime.combine(d, datetime.min.time()) + timedelta(hours=9 + i)
            end_dt = start_dt + timedelta(minutes=int(task.get("est_min") or 30))
            uid = f"{plan.get('id', 'plan')}-{entry['date']}-{task.get('id', i)}@life-mentor"
            desc = f"验收标准：{task.get('verify', '')}"
            if entry.get("phase"):
                desc += f" ｜ {entry['phase']}"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{start_dt:%Y%m%dT%H%M%S}",
                f"DTEND:{end_dt:%Y%m%dT%H%M%S}",
                _fold(f"SUMMARY:{_esc(task.get('title', '任务'))}"),
                _fold(f"DESCRIPTION:{desc}"),
                "CATEGORIES:LIFE-MENTOR",
                "END:VEVENT",
            ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
