#!/usr/bin/env python3
"""校验层：把 planning.md 里写的硬约束变成代码，拦住「看起来很美但执行不了」的计划。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .cal import parse_date

MAX_TASKS_PER_DAY = 3
MAX_TASK_MINUTES = 90
MAX_DAY_MINUTES = 240
MIN_BUFFER_PER_WEEK = 1
REQUIRED_TASK_FIELDS = ("id", "title", "est_min", "verify")


def validate_plan(plan: dict[str, Any], profile: dict[str, Any] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for field in ("id", "goal", "start_date", "end_date", "days"):
        if not plan.get(field):
            errors.append(f"缺少必填字段：{field}")
    if errors:
        return errors, warnings

    try:
        start = parse_date(plan["start_date"])
        end = parse_date(plan["end_date"])
    except Exception as exc:  # noqa: BLE001
        return [f"日期无法解析：{exc}"], warnings

    if end < start:
        errors.append("end_date 早于 start_date")
        return errors, warnings

    # 1) 日期必须连续覆盖，一天都不能缺
    days = plan["days"]
    got = [d.get("date") for d in days]
    expected = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    if got != expected:
        missing = sorted(set(expected) - set(got))
        extra = sorted(set(got) - set(expected))
        if missing:
            errors.append(f"日期不连续，缺失 {len(missing)} 天（如 {missing[0]}）")
        if extra:
            errors.append(f"存在超出周期的日期：{extra[:3]}")
        if not missing and not extra:
            errors.append("日期顺序错乱，必须按升序排列")

    # 2) 任务粒度
    budget = int((profile or {}).get("constraints", {}).get("time_per_day_min", 120) or 120)
    budget = min(budget, MAX_DAY_MINUTES) if budget > 0 else 120
    seen_ids: set[str] = set()
    dup_ids: list[str] = []
    for entry in days:
        d = entry.get("date", "?")
        tasks = entry.get("tasks", [])
        is_buffer = bool(entry.get("is_buffer")) or parse_date(d).weekday() == int(plan.get("buffer_weekday", 6))
        if len(tasks) > MAX_TASKS_PER_DAY:
            errors.append(f"{d}：{len(tasks)} 项任务，超过单日上限 {MAX_TASKS_PER_DAY}")
        if is_buffer and tasks:
            warnings.append(f"{d}：缓冲日安排了任务，建议留空")
        total = 0
        for t in tasks:
            for f in REQUIRED_TASK_FIELDS:
                if not t.get(f):
                    errors.append(f"{d}：任务缺少字段 {f}（{t.get('title', '未命名')}）")
            tid = t.get("id")
            if tid in seen_ids:
                dup_ids.append(tid)
            seen_ids.add(tid)
            mins = int(t.get("est_min") or 0)
            total += mins
            if mins > MAX_TASK_MINUTES:
                errors.append(f"{d}：任务「{t.get('title')}」{mins}min，超过单任务上限 {MAX_TASK_MINUTES}min，请拆分")
            if mins <= 0:
                errors.append(f"{d}：任务「{t.get('title')}」est_min 必须为正数")
        if total > budget:
            warnings.append(f"{d}：当日总计 {total}min，超过档案里的可用时间 {budget}min")
    if dup_ids:
        errors.append(f"任务 id 重复：{sorted(set(dup_ids))[:5]}")

    # 3) 每周至少留一天缓冲
    week_days: dict[str, list[dict]] = {}
    for entry in days:
        d = parse_date(entry["date"])
        key = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        week_days.setdefault(key, []).append(entry)
    for wk, entries in week_days.items():
        if len(entries) < 7:
            continue  # 不完整的周不强制
        buffers = sum(
            1 for e in entries
            if e.get("is_buffer") or not e.get("tasks")
        )
        if buffers < MIN_BUFFER_PER_WEEK:
            warnings.append(f"{wk}：7 天排满无缓冲日，断签风险高")

    # 4) 阶段表
    for ph in plan.get("phases", []):
        for f in ("name", "start", "end"):
            if not ph.get(f):
                errors.append(f"阶段缺少字段 {f}")
                break

    return errors, warnings
