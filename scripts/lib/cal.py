#!/usr/bin/env python3
"""日期层：所有日期算术集中在这里，绝不让 LLM 算日子。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from .store import MentorError

WEEKDAY_CN = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
DEFAULT_BUFFER_WEEKDAY = 6  # 周日作为缓冲日


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise MentorError(f"日期格式不对：{value!r}，应为 YYYY-MM-DD") from exc


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise MentorError(f"结束日期 {end} 早于开始日期 {start}")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_bounds(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def weekday_cn(d: date) -> str:
    return WEEKDAY_CN[d.weekday()]


def phase_for(d: date, phases: Iterable[dict]) -> str:
    for ph in phases:
        if parse_date(ph["start"]) <= d <= parse_date(ph["end"]):
            return ph.get("name", "")
    return ""


def day_index(d: date, start: date) -> int:
    """第几天，从 1 开始。"""
    return (d - start).days + 1


def is_buffer_day(d: date, plan: dict) -> bool:
    if d.isoformat() in plan.get("buffer_days", []):
        return True
    return d.weekday() == int(plan.get("buffer_weekday", DEFAULT_BUFFER_WEEKDAY + 0))
