#!/usr/bin/env python3
"""用 Python 版算法生成对照基准，供 tools/parity-check.js 校验 JS 版是否一致。

为什么需要这个：两端算法各写一遍，最容易出现「看起来都对、数字差一点」的隐性偏差。
基准由 Python 端产出，JS 端只能被动对齐，谁也不能自说自话。

用法：
    python tools/gen-parity-fixture.py > tools/parity-fixture.json
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.stats import compute, week_stats  # noqa: E402
from lib.cal import week_key  # noqa: E402

START = date(2026, 11, 9)
N = 14
REF = date(2026, 11, 22)

days = []
for i in range(N):
    d = START + timedelta(days=i)
    days.append({
        "date": d.isoformat(),
        "tasks": [{"id": f"t{i}", "title": f"任务{i}", "est_min": 30, "verify": "x"}],
    })

plan = {
    "id": "parity",
    "version": 1,
    "goal": "一致性测试",
    "start_date": START.isoformat(),
    "end_date": (START + timedelta(days=N - 1)).isoformat(),
    "days": days,
    "phases": [],
}

# 场景：{序号: 状态}，未指定的日子默认 done
SCENARIOS = {
    "all_done": {},
    "one_missing_in_week": {3: "missing"},
    "two_missing_same_week": {2: "missing", 3: "missing"},
    "missing_across_weeks": {3: "missing", 10: "missing"},
    "with_skip": {2: "missing", 9: "skip"},
    "with_blocked": {5: "blocked"},
    "mixed": {2: "missing", 4: "partial", 7: "blocked", 9: "skip", 11: "missing", 12: "partial"},
    "trailing_missing": {11: "missing", 12: "missing", 13: "missing"},
}


def build_logs(pattern):
    logs = {}
    for i in range(N):
        key = days[i]["date"]
        st = pattern.get(i, "done")
        logs[key] = {
            "date": key,
            "at": key + "T21:00:00",
            "status": st,
            "done_tasks": [f"t{i}"] if st == "done" else ([] if st != "partial" else []),
            "note": "",
            "energy": 3,
        }
    return logs


def snapshot(pattern, grace):
    logs = build_logs(pattern)
    s = compute(plan, logs, ref=REF, profile={"resilience": {"grace_per_week": grace, "max_carry_days": 2}})
    w = week_stats(plan, logs, REF)
    return {
        "streak": s["streak"],
        "best_streak": s["best_streak"],
        "cumulative_days": s["cumulative_days"],
        "effective_days": s["effective_days"],
        "done_tasks": s["done_tasks"],
        "day_rate": round(s["day_rate"], 6),
        "percent": s["percent"],
        "carryover": len(s["carryover"]),
        "carryover_dates": sorted({c["from_date"] for c in s["carryover"]}),
        "blocked_dates": s["blocked_dates"],
        "skipped_dates": s["skipped_dates"],
        "missing_dates": s["missing_dates"],
        "grace_weeks_used": s["grace_weeks_used"],
        "needs_adapt": s["needs_adapt"],
        "week_key": w["week"],
        "week_planned_days": w["planned_days"],
        "week_score": round(w["score"], 6),
    }


cases = []
for name, pattern in SCENARIOS.items():
    cases.append({"name": name, "grace": 1, "logs": build_logs(pattern), "expect": snapshot(pattern, 1)})

# 关闭豁免：同样场景应更早断签
cases.append({"name": "one_missing_grace_off", "grace": 0,
              "logs": build_logs({3: "missing"}), "expect": snapshot({3: "missing"}, 0)})

# 顺延上限为 0
cases.append({"name": "carry_disabled", "grace": 1, "max_carry": 0,
              "logs": build_logs({11: "missing", 12: "partial"}),
              "expect": None})
last = cases[-1]
s0 = compute(plan, last["logs"], ref=REF, profile={"resilience": {"grace_per_week": 1, "max_carry_days": 0}})
last["expect"] = dict(snapshot({11: "missing", 12: "partial"}, 1))
last["expect"]["carryover"] = len(s0["carryover"])
last["expect"]["carryover_dates"] = sorted({c["from_date"] for c in s0["carryover"]})

out = {
    "generated_by": "tools/gen-parity-fixture.py",
    "plan": plan,
    "ref": REF.isoformat(),
    "week_keys": {d.isoformat(): week_key(d) for d in (START, date(2026, 11, 18), date(2027, 1, 1))},
    "cases": cases,
}
print(json.dumps(out, ensure_ascii=False, indent=1))
