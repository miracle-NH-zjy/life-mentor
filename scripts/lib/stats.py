#!/usr/bin/env python3
"""统计层：把 plan + logs 压成一份可被 CLI / LLM 消费的指标快照。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .cal import date_range, parse_date, phase_for, week_key
from .store import today

SCORE = {"done": 1.0, "partial": 0.5, "skip": 0.0, "blocked": 0.0}


def _day_status(day_log: dict[str, Any] | None) -> str:
    return (day_log or {}).get("status", "missing")


def compute(plan: dict[str, Any], latest_logs: dict[str, dict], ref: date | None = None) -> dict[str, Any]:
    ref = ref or today()
    days = plan.get("days", [])
    start = parse_date(plan["start_date"])
    end = parse_date(plan["end_date"])

    elapsed = [d for d in date_range(start, min(end, ref))]
    remain = list(date_range(ref + timedelta(days=1), end)) if ref < end else []
    # 完成率只统计「已结束的日子」，今天还没过完不算失分
    settled = [d for d in elapsed if d < ref]

    total_tasks = sum(len(d.get("tasks", [])) for d in days)
    done_tasks = sum(len(log.get("done_tasks", [])) for log in
                     (latest_logs.get(d["date"], {}) for d in days))
    done_tasks = min(done_tasks, total_tasks)

    scored: list[float] = []
    blocked, skipped, missing = [], [], []
    by_date = {d["date"]: d for d in days}

    for d in elapsed:
        log = latest_logs.get(d.isoformat())
        st = _day_status(log)
        if st == "blocked":
            blocked.append(d.isoformat())
        elif st == "skip":
            skipped.append(d.isoformat())
        elif st == "missing" and d < ref:
            missing.append(d.isoformat())
    for d in settled:
        scored.append(SCORE.get(_day_status(latest_logs.get(d.isoformat())), 0.0))

    # 最佳连击：完整历史里最长的一段
    best = run = 0
    for d in date_range(start, min(end, ref)):
        if _day_status(latest_logs.get(d.isoformat())) in ("done", "partial"):
            run += 1
            best = max(best, run)
        else:
            run = 0

    # 当前连击：今天没打卡就从昨天往前数；空任务日（缓冲）不打断也不计数
    probe = ref
    if _day_status(latest_logs.get(ref.isoformat())) not in ("done", "partial"):
        probe = ref - timedelta(days=1)
    streak = 0
    while probe >= start:
        st = _day_status(latest_logs.get(probe.isoformat()))
        entry = by_date.get(probe.isoformat())
        if st in ("done", "partial"):
            streak += 1
        elif st == "missing" and entry is not None and not entry.get("tasks"):
            pass  # 缓冲日没打卡，中性
        else:
            break
        probe -= timedelta(days=1)

    day_rate = (sum(scored) / len(scored)) if scored else 0.0

    by_phase: dict[str, dict[str, Any]] = {}
    for d in settled:
        ph = phase_for(d, plan.get("phases", [])) or "未分组"
        bucket = by_phase.setdefault(ph, {"days": 0, "score": 0.0})
        bucket["days"] += 1
        bucket["score"] += SCORE.get(_day_status(latest_logs.get(d.isoformat())), 0.0)

    today_entry = next((d for d in days if d["date"] == ref.isoformat()), None)
    next_tasks = []
    if today_entry:
        done_ids = set((latest_logs.get(ref.isoformat()) or {}).get("done_tasks", []))
        next_tasks = [t for t in today_entry.get("tasks", []) if t.get("id") not in done_ids]

    return {
        "plan_id": plan.get("id"),
        "version": plan.get("version", 1),
        "goal": plan.get("goal", ""),
        "domain": plan.get("domain", ""),
        "start_date": plan["start_date"],
        "end_date": plan["end_date"],
        "total_days": len(days),
        "elapsed_days": len(elapsed),
        "remaining_days": len(remain),
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "task_rate": (done_tasks / total_tasks) if total_tasks else 0.0,
        "day_rate": day_rate,
        "percent": round(100 * len(elapsed) / len(days), 1) if days else 0.0,
        "streak": streak,
        "best_streak": best,
        "blocked_dates": blocked,
        "skipped_dates": skipped,
        "missing_dates": missing,
        "by_phase": by_phase,
        "today": ref.isoformat(),
        "today_entry": today_entry,
        "today_pending_tasks": next_tasks,
        "today_log": latest_logs.get(ref.isoformat()),
        "week": week_key(ref),
        "needs_adapt": len(elapsed) >= 7 and day_rate < 0.5,
        "in_range": start <= ref <= end,
    }


def week_slice(plan: dict[str, Any], latest_logs: dict[str, dict], ref: date) -> list[dict[str, Any]]:
    monday = ref - timedelta(days=ref.weekday())
    out = []
    for d in date_range(monday, monday + timedelta(days=6)):
        entry = next((x for x in plan.get("days", []) if x["date"] == d.isoformat()), None)
        out.append({
            "date": d.isoformat(),
            "plan": entry,
            "log": latest_logs.get(d.isoformat()),
        })
    return out


def week_stats(plan: dict[str, Any], latest_logs: dict[str, dict], ref: date) -> dict[str, Any]:
    rows = week_slice(plan, latest_logs, ref)
    planned = [r for r in rows if r["plan"]]
    # 分母只算已过完的日子，未来几天不该拉低本周成绩
    settled = [r for r in planned if parse_date(r["date"]) < today()]
    scored = [SCORE.get(_day_status(r["log"]), 0.0) for r in settled]
    return {
        "week": week_key(ref),
        "planned_days": len(planned),
        "settled_days": len(settled),
        "logged_days": sum(1 for r in rows if r["log"]),
        "score": round(sum(scored) / len(scored), 3) if scored else 0.0,
        "rows": rows,
    }
