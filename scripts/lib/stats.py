#!/usr/bin/env python3
"""统计层：把 plan + logs 压成一份可被 CLI / LLM 消费的指标快照。

宽容原则（对应 profile.resilience）：
· 累计天数永不归零，一次中断不会让之前的努力作废
· 每周允许 grace_per_week 天缺勤不打断连击（自动生效，无需操作）
· 主动 skip 是计划的一部分，不算断签；blocked 如实上报，同样不打断
· 未完成的任务顺延 max_carry_days 天，过期才真正失效
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .cal import date_range, parse_date, phase_for, week_key
from .store import today

SCORE = {"done": 1.0, "partial": 0.5, "skip": 0.0, "blocked": 0.0}
RECORDED = ("done", "partial", "skip", "blocked")

DEFAULT_RESILIENCE = {"grace_per_week": 1, "max_carry_days": 2, "count_skip_as_break": False}


def _resilience(profile: dict | None) -> dict:
    cfg = dict(DEFAULT_RESILIENCE)
    cfg.update((profile or {}).get("resilience") or {})
    return cfg


def _day_status(day_log: dict[str, Any] | None) -> str:
    return (day_log or {}).get("status", "missing")


def _is_rest_day(entry: dict | None) -> bool:
    """没有任务的日子（缓冲日/休息日）不参与连击判定。"""
    return entry is not None and not entry.get("tasks")


def compute(plan: dict[str, Any], latest_logs: dict[str, dict],
            ref: date | None = None, profile: dict | None = None) -> dict[str, Any]:
    ref = ref or today()
    days = plan.get("days", [])
    start = parse_date(plan["start_date"])
    end = parse_date(plan["end_date"])
    cfg = _resilience(profile)
    grace_per_week = max(0, int(cfg["grace_per_week"]))
    max_carry = max(0, int(cfg["max_carry_days"]))

    elapsed = [d for d in date_range(start, min(end, ref))]
    remain = list(date_range(ref + timedelta(days=1), end)) if ref < end else []
    settled = [d for d in elapsed if d < ref]

    by_date = {d["date"]: d for d in days}
    total_tasks = sum(len(d.get("tasks", [])) for d in days)
    done_tasks = sum(len(log.get("done_tasks", [])) for log in
                     (latest_logs.get(d["date"], {}) for d in days))
    done_tasks = min(done_tasks, total_tasks)

    blocked, skipped, missing = [], [], []
    cumulative = effective = 0
    for d in elapsed:
        st = _day_status(latest_logs.get(d.isoformat()))
        if st in RECORDED:
            cumulative += 1
        if st in ("done", "partial"):
            effective += 1
        if st == "blocked":
            blocked.append(d.isoformat())
        elif st == "skip":
            skipped.append(d.isoformat())
        elif st == "missing" and d < ref:
            missing.append(d.isoformat())

    scored = [SCORE.get(_day_status(latest_logs.get(d.isoformat())), 0.0) for d in settled]
    day_rate = (sum(scored) / len(scored)) if scored else 0.0

    # ---- 连击（宽容版）：从近到远遍历，每周首次缺勤使用豁免
    streak, grace_weeks_used = _walk_streak(
        list(reversed(elapsed)), latest_logs, by_date, grace_per_week
    )
    best = _best_streak(date_range(start, min(end, ref)), latest_logs, by_date, grace_per_week)

    by_phase: dict[str, dict[str, Any]] = {}
    for d in settled:
        ph = phase_for(d, plan.get("phases", [])) or "未分组"
        bucket = by_phase.setdefault(ph, {"days": 0, "score": 0.0})
        bucket["days"] += 1
        bucket["score"] += SCORE.get(_day_status(latest_logs.get(d.isoformat())), 0.0)

    today_entry = by_date.get(ref.isoformat())
    next_tasks = []
    if today_entry:
        done_ids = set((latest_logs.get(ref.isoformat()) or {}).get("done_tasks", []))
        next_tasks = [t for t in today_entry.get("tasks", []) if t.get("id") not in done_ids]

    carry = carryover(plan, latest_logs, ref, max_carry)

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
        "cumulative_days": cumulative,
        "effective_days": effective,
        "grace_weeks_used": sorted(grace_weeks_used),
        "grace_per_week": grace_per_week,
        "carryover": carry,
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


def _walk_streak(order: list[date], latest_logs: dict[str, dict],
                 by_date: dict[str, dict], grace_per_week: int) -> tuple[int, set[str]]:
    """order 为从近到远的日期序列。返回 (当前连击, 该段内用过豁免的周)。"""
    streak = 0
    used: dict[str, int] = {}
    for d in order:
        st = _day_status(latest_logs.get(d.isoformat()))
        entry = by_date.get(d.isoformat())
        if st in RECORDED:
            streak += 1
            continue
        if _is_rest_day(entry):
            continue  # 休息日：中性，不打断也不计数
        wk = week_key(d)
        if used.get(wk, 0) < grace_per_week:
            used[wk] = used.get(wk, 0) + 1
            continue  # 本周还有豁免额度，不追究
        break
    return streak, set(used)


def _best_streak(order: list[date], latest_logs: dict[str, dict],
                 by_date: dict[str, dict], grace_per_week: int) -> int:
    best = run = 0
    used: dict[str, int] = {}
    for d in order:
        st = _day_status(latest_logs.get(d.isoformat()))
        entry = by_date.get(d.isoformat())
        if st in RECORDED:
            run += 1
        elif _is_rest_day(entry):
            continue
        else:
            wk = week_key(d)
            if used.get(wk, 0) < grace_per_week:
                used[wk] = used.get(wk, 0) + 1
                continue
            best = max(best, run)
            run = 0
    return max(best, run)


def carryover(plan: dict[str, Any], latest_logs: dict[str, dict],
              ref: date, max_days: int) -> list[dict[str, Any]]:
    """过去 max_days 天内没做完、且没被主动跳过的任务。过期即失效。"""
    if max_days <= 0:
        return []
    by_date = {d["date"]: d for d in plan.get("days", [])}
    out: list[dict[str, Any]] = []
    for offset in range(1, max_days + 1):
        d = ref - timedelta(days=offset)
        entry = by_date.get(d.isoformat())
        if not entry:
            continue
        log = latest_logs.get(d.isoformat()) or {}
        if log.get("status") == "skip":
            continue  # 主动跳过 = 放弃这批任务，不顺延
        done_ids = set(log.get("done_tasks", []))
        for t in entry.get("tasks", []):
            if t.get("id") in done_ids:
                continue
            out.append({
                "task": t,
                "from_date": d.isoformat(),
                "age_days": offset,
                "expires_in": max_days - offset,
            })
    return out


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
