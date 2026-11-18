#!/usr/bin/env python3
"""life-mentor · 人生导师模拟器 CLI

设计原则：LLM 负责诊断与内容生成，本脚本负责所有确定性计算与状态持久化。
零第三方依赖，Python 3.9+ 可直接运行。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib import motivation, render
from lib import ics as ics_mod
from lib.cal import date_range, parse_date, phase_for, week_key, weekday_cn, week_bounds
from lib.stats import compute, week_stats
from lib.store import MentorError, Store, now_iso, read_json, today
from lib.validate import validate_plan

try:  # Windows 终端默认 GBK，中文会炸
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


# ------------------------------------------------------------------ 工具


def _store(args) -> Store:
    return Store.open(getattr(args, "root", None))


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _load_plan(args) -> tuple[Store, dict]:
    store = _store(args)
    return store, store.load_plan(getattr(args, "plan_id", None))


def _deep_set(target: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    cur = target
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = value


def _parse_value(raw: str):
    """`k=1` 里的 1 要变成数字，`k=[a,b]` 要变成列表。"""
    if raw.startswith("+"):
        return raw[1:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


# ------------------------------------------------------------------ init


def cmd_init(args) -> int:
    root = Path(args.dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    store = Store.create(root, force=args.force)
    profile = {
        "schema": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "name": args.name or "",
        "identity": "",
        "history": [],
        "goal": {
            "statement": args.goal or "",
            "deadline": "",
            "success_criteria": "",
        },
        "constraints": {
            "time_per_day_min": args.time_per_day,
            "money": "",
            "health": [],
            "other": [],
        },
        "resources": [],
        "risks": [],
        "strengths": [],
        "weaknesses": [],
        "preferences": {
            "tone": args.tone,
            "checkin_time": args.checkin_time,
            "language": "zh",
        },
        "resilience": {
            "grace_per_week": args.grace_per_week,
            "max_carry_days": args.max_carry_days,
            "count_skip_as_break": False,
        },
        "motivation": {
            "enabled": True,
            "mode": "mix",
            "custom": {},
        },
    }
    store.save_profile(profile)
    print(f"✓ 档案已创建：{store.profile_path}")
    print(f"✓ 目录：{store.base}")
    print()
    print("下一步：")
    print("  1) 补全档案：python scripts/mentor.py profile set --set identity=学生 --set goal.deadline=2027-04-30")
    print("  2) 生成计划骨架：python scripts/mentor.py plan scaffold --goal \"...\" --start 2026-11-18 --days 30 -o plan.json")
    print("  3) 填完后导入：python scripts/mentor.py plan new --file plan.json")
    return 0


# ------------------------------------------------------------------ profile


def cmd_profile(args) -> int:
    store = _store(args)
    profile = store.load_profile()

    if args.action == "show":
        if args.json:
            _print_json(profile)
        else:
            print(f"姓名：{profile.get('name') or '（未填）'}  身份：{profile.get('identity') or '（未填）'}")
            goal = profile.get("goal", {})
            print(f"目标：{goal.get('statement') or '（未填）'}  截止：{goal.get('deadline') or '（未填）'}")
            c = profile.get("constraints", {})
            print(f"每日可用：{c.get('time_per_day_min')}min  资金：{c.get('money') or '（未填）'}")
            print(f"健康约束：{', '.join(c.get('health') or []) or '（未填）'}")
            print(f"人格模式：{profile.get('preferences', {}).get('tone', 'auto')}")
            if profile.get("history"):
                print(f"经历条目：{len(profile['history'])} 条")
        return 0

    # set
    changed = 0
    for pair in args.set or []:
        if "=" not in pair:
            raise MentorError(f"--set 需要 key=value 形式，收到：{pair}")
        key, raw = pair.split("=", 1)
        _deep_set(profile, key.strip(), _parse_value(raw.strip()))
        changed += 1

    if args.patch:
        patch = read_json(Path(args.patch))
        _merge(profile, patch)
        changed += 1

    if not changed:
        raise MentorError("没有要改的内容。用 --set key=value 或 --patch file.json")

    store.save_profile(profile)
    print(f"✓ 档案已更新（{changed} 处改动）")
    return 0


def _merge(base: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        elif isinstance(v, list) and isinstance(base.get(k), list) and not v:
            base[k] = []  # 空列表显式清空
        else:
            base[k] = v
    return base


# ------------------------------------------------------------------ plan


def cmd_plan_scaffold(args) -> int:
    store = _store(args)
    profile = store.load_profile()
    start = parse_date(args.start) if args.start else today()
    days_count = args.days
    end = start + timedelta(days=days_count - 1)
    plan_id = args.id or f"plan-{start:%Y-%m}"

    days = []
    for i, d in enumerate(date_range(start, end)):
        days.append({
            "date": d.isoformat(),
            "weekday": weekday_cn(d),
            "phase": "",
            "is_buffer": d.weekday() == args.buffer_weekday,
            "tasks": [],
        })

    skeleton = {
        "id": plan_id,
        "version": 0,
        "goal": args.goal or profile.get("goal", {}).get("statement", ""),
        "domain": args.domain or "",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "buffer_weekday": args.buffer_weekday,
        "status": "active",
        "phases": [
            {"name": "第一阶段", "start": start.isoformat(),
             "end": (start + timedelta(days=days_count // 2 - 1)).isoformat(),
             "focus": "先写清楚这一段要达到什么"},
            {"name": "第二阶段", "start": (start + timedelta(days=days_count // 2)).isoformat(),
             "end": end.isoformat(), "focus": ""},
        ],
        "days": days,
        "history": [],
        "notes": "由 plan scaffold 生成的骨架。填完 phases 与每天的 tasks 后，用 plan new --file 导入。",
    }

    text = json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"✓ 骨架已写入：{out}（{days_count} 天，{start} → {end}）")
        print("  现在把每天的 tasks 填上，每项必须含 id / title / est_min / verify。")
    else:
        print(text)
    return 0


def _normalize(plan: dict) -> None:
    """补齐可以推导的字段，让 LLM 少填一些容易错的东西。"""
    plan.setdefault("status", "active")
    plan.setdefault("version", 0)
    plan.setdefault("buffer_weekday", 6)
    for entry in plan.get("days", []):
        d = parse_date(entry["date"])
        entry.setdefault("weekday", weekday_cn(d))
        if not entry.get("phase"):
            entry["phase"] = phase_for(d, plan.get("phases", []))
        entry.setdefault("is_buffer", d.weekday() == int(plan.get("buffer_weekday", 6)))
        for i, t in enumerate(entry.get("tasks", []), 1):
            t.setdefault("id", f"d{entry['date'].replace('-', '')}t{i}")


def cmd_plan_new(args) -> int:
    store = _store(args)
    plan = read_json(Path(args.file))
    _normalize(plan)
    profile = store.load_profile()
    errors, warns = validate_plan(plan, profile)

    for w in warns:
        print(f"  ⚠ {w}")
    if errors:
        print("\n✗ 校验未通过（这些是硬约束，不是建议）：")
        for e in errors:
            print(f"  - {e}")
        if not args.force:
            print("\n修正后重试。确实要跳过校验请加 --force，但计划大概率执行不了。")
            return 1
        print("\n--force 已指定，跳过校验继续保存。")

    exists = store.plan_path(plan["id"]).is_file()
    if exists and not (args.replace or args.force):
        print(f"✗ 计划 {plan['id']} 已存在。")
        print("  想调整用 plan amend；想推翻重来加 --replace。")
        return 1

    path = store.save_plan(plan, action="create" if not exists else "replace")
    print(f"\n✓ 计划已保存：{path}（v{plan['version']}，{len(plan['days'])} 天）")
    print("  下一步：python scripts/mentor.py status")
    return 0


def cmd_plan_amend(args) -> int:
    store = _store(args)
    current = store.load_plan(args.plan_id)
    patch = read_json(Path(args.file))
    from_date = patch.get("from_date") or today().isoformat()
    from_d = parse_date(from_date)
    end_d = parse_date(current["end_date"])

    if from_d > end_d:
        raise MentorError(f"from_date {from_date} 超出计划结束日 {current['end_date']}")

    new_days = patch.get("days", [])
    new_dates = [d["date"] for d in new_days]
    expected = [d.isoformat() for d in date_range(from_d, end_d)]
    if new_dates != expected:
        raise MentorError(
            f"amend 的 days 必须从 {from_date} 连续覆盖到 {current['end_date']}"
            f"（需要 {len(expected)} 天，实际 {len(new_dates)} 天）"
        )

    kept = [d for d in current["days"] if parse_date(d["date"]) < from_d]
    merged = {
        **current,
        "days": kept + new_days,
        "phases": patch.get("phases", current.get("phases", [])),
        "goal": patch.get("goal", current.get("goal")),
    }
    _normalize(merged)

    profile = store.load_profile()
    errors, warns = validate_plan(merged, profile)
    for w in warns:
        print(f"  ⚠ {w}")
    if errors and not args.force:
        print("\n✗ 调整后的计划校验未通过：")
        for e in errors:
            print(f"  - {e}")
        return 1

    reason = args.reason or patch.get("reason") or "未说明原因"
    merged["history"] = current.get("history", [])
    merged["history"].append({
        "version": current.get("version", 1) + 1,
        "at": now_iso(),
        "action": "amend",
        "from_date": from_date,
        "reason": reason,
    })
    path = store.save_plan(merged, action="amend")
    print(f"✓ 已调整 {from_date} 起共 {len(new_days)} 天（v{merged['version']}）")
    print(f"  原因：{reason}")
    print(f"  旧版本已归档：plans/archive/{merged['id']}.v{current.get('version', 1)}.json")
    return 0


def cmd_plan_show(args) -> int:
    store, plan = _load_plan(args)
    latest = store.latest_logs_by_date()

    if args.all:
        print(render.plan_markdown(plan, latest))
        return 0

    if args.week:
        ref = parse_date(args.date) if args.date else today()
        ws = week_stats(plan, latest, ref)
        print(render.week_view(ws, plan))
        return 0

    target = parse_date(args.date) if args.date else today()
    entry = next((d for d in plan["days"] if d["date"] == target.isoformat()), None)
    if not entry:
        raise MentorError(
            f"{target} 不在计划周期内（{plan['start_date']} → {plan['end_date']}）"
        )
    print(render.day_card(entry, latest.get(entry["date"]), plan))
    return 0


def cmd_plan_list(args) -> int:
    store = _store(args)
    ids = store.plan_ids()
    if not ids:
        print("还没有计划。先运行 plan scaffold / plan new。")
        return 0
    for pid in ids:
        plan = store.load_plan(pid)
        print(f"{pid}  v{plan.get('version', 1)}  {plan.get('start_date')} → {plan.get('end_date')}"
              f"  [{plan.get('status')}]  {plan.get('goal', '')[:30]}")
        for h in plan.get("history", [])[-3:]:
            print(f"    · v{h.get('version')} {h.get('at', '')[:10]} {h.get('action')}"
                  f"{(' — ' + h['reason']) if h.get('reason') else ''}")
    return 0


# ------------------------------------------------------------------ checkin


def cmd_checkin(args) -> int:
    store = _store(args)
    plan = store.load_plan(args.plan_id)
    d = parse_date(args.date) if args.date else today()
    if d > today():
        raise MentorError(f"不能给未来日期打卡：{d}（今天 {today()}）")
    entry = next((x for x in plan["days"] if x["date"] == d.isoformat()), None)
    if not entry:
        raise MentorError(
            f"{d} 不在计划周期内（{plan['start_date']} → {plan['end_date']}）。\n"
            f"  查一下：python scripts/mentor.py plan show --date {d}"
        )

    valid = [t["id"] for t in entry.get("tasks", [])]
    if args.tasks:
        done = [t.strip() for t in args.tasks.split(",") if t.strip()]
        bad = [t for t in done if t not in valid]
        if bad:
            raise MentorError(
                f"任务 id 不存在：{bad}\n  当天可选：{valid or '（无任务）'}"
            )
    elif args.status == "done":
        done = list(valid)
    else:
        done = []

    evidence: list[str] = []
    for raw in (args.evidence or []):
        for item in raw.split(","):
            item = item.strip()
            if item:
                evidence.append(store.save_evidence(item, d))

    record = {
        "date": d.isoformat(),
        "at": now_iso(),
        "status": args.status,
        "done_tasks": done,
        "note": args.note or "",
        "energy": args.energy,
        "evidence": evidence,
    }
    store.append_log(record)

    profile = store.load_profile()
    latest = store.latest_logs_by_date()
    stats = compute(plan, latest, profile=profile)  # 始终以「今天」为参照

    print(f"✓ 已打卡：{d} · {render.STATUS_LABEL[args.status]}"
          f"（{len(done)}/{len(valid)} 项）")
    if evidence:
        print(f"  凭证 {len(evidence)} 个 → .mentor/evidence/{d:%Y-%m}/")
    print(f"  累计 {stats['cumulative_days']} 天（有效 {stats['effective_days']}）"
          f" | 当前连击 {stats['streak']} 天"
          f" | 日均完成率 {round(stats['day_rate'] * 100)}%")

    scene = {"done": "done", "partial": "done", "skip": "skip", "blocked": "blocked"}[args.status]
    recent_missing = [x for x in stats["missing_dates"]
                      if (d - timedelta(days=3)).isoformat() <= x < d.isoformat()]
    if recent_missing and args.status in ("done", "partial"):
        scene = "recovery"
    if scene == "done" and stats["cumulative_days"] in (7, 14, 21, 30, 60, 100):
        scene = "milestone"

    quote = motivation.pick(profile, scene, {
        "streak": stats["streak"],
        "cumulative": stats["cumulative_days"],
        "days": stats["cumulative_days"],
        "percent": round(stats["percent"]),
        "name": profile.get("name", ""),
    })
    if quote:
        print()
        print(f"  「{quote}」")
        motivation.remember(store, quote)

    if args.status == "blocked":
        recent = [x for x in stats["blocked_dates"] if x >= (d - timedelta(days=6)).isoformat()]
        if len(recent) >= 2:
            print()
            print(f"  ⚠ 近 7 天已有 {len(recent)} 天标记受阻。连续受阻说明计划假设错了，不是你不努力。")
            print("    建议：python scripts/mentor.py review 然后 plan amend 下调强度。")
    if stats["needs_adapt"]:
        print("  ⚠ 完成率持续低于 50%，计划需要下调。用 review 看卡点再 amend。")
    if stats["carryover"]:
        print(f"  ↻ 还有 {len(stats['carryover'])} 项待补任务，顺延期内不算失效。")
    return 0


# ------------------------------------------------------------------ status / review


def cmd_status(args) -> int:
    store, plan = _load_plan(args)
    profile = store.load_profile()
    stats = compute(plan, store.latest_logs_by_date(), profile=profile)
    if args.json:
        _print_json(stats)
        return 0
    print(render.status_view(stats, plan))
    blocked_recently = bool(stats["blocked_dates"]) and \
        stats["blocked_dates"][-1] >= (today() - timedelta(days=2)).isoformat()
    today_status = (stats.get("today_log") or {}).get("status")
    scene = None
    if stats["needs_adapt"]:
        scene = "low"
    elif blocked_recently and today_status not in ("done", "partial"):
        scene = "blocked"  # 今天已完成就不再泼冷水
    if scene:
        quote = motivation.pick(profile, scene, {
            "streak": stats["streak"], "cumulative": stats["cumulative_days"],
            "percent": round(stats["percent"]), "days": stats["cumulative_days"],
            "name": profile.get("name", ""),
        })
        if quote:
            print()
            print(f"  「{quote}」")
    return 0


def cmd_review(args) -> int:
    store, plan = _load_plan(args)
    latest = store.latest_logs_by_date()
    if args.week:
        year, week = args.week.split("-W")
        from datetime import date as _d
        ref = _d.fromisocalendar(int(year), int(week), 1)
    else:
        ref = today()
    ws = week_stats(plan, latest, ref)
    stats = compute(plan, latest, ref=ref, profile=store.load_profile())

    text = render.review_markdown(stats, ws, plan)
    path = store.save_review(ws["week"], text)

    if args.json:
        _print_json({
            "week": ws["week"],
            "week_score": ws["score"],
            "planned_days": ws["planned_days"],
            "logged_days": ws["logged_days"],
            "day_rate": round(stats["day_rate"], 3),
            "streak": stats["streak"],
            "blocked": stats["blocked_dates"],
            "skipped": stats["skipped_dates"],
            "missing": stats["missing_dates"],
            "needs_adapt": stats["needs_adapt"],
            "review_path": str(path),
        })
    else:
        print(f"✓ 复盘已生成：{path}")
        print(f"  本周完成度 {round(ws['score'] * 100)}%"
              f"（已结束 {ws.get('settled_days', 0)} 天，打卡 {ws['logged_days']} 天）")
        print(f"  连续 {stats['streak']} 天 | 日均完成率 {round(stats['day_rate'] * 100)}%")
        print("  归因与调整两节留空，由导师填写后即可作为下一轮 amend 的依据。")
    return 0


# ------------------------------------------------------------------ export / doctor


def cmd_export(args) -> int:
    store, plan = _load_plan(args)
    latest = store.latest_logs_by_date()
    if args.format == "ics":
        text = ics_mod.to_ics(plan, latest, only_pending=args.pending)
        default_name = f"{plan['id']}.ics"
    else:
        text = render.plan_markdown(plan, latest)
        default_name = f"{plan['id']}.md"

    out = Path(args.out) if args.out else store.export_path(default_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"✓ 已导出：{out}")
    return 0


def cmd_doctor(args) -> int:
    store = _store(args)
    problems: list[str] = []
    notes: list[str] = []

    if not store.has_profile():
        problems.append("档案缺失：.mentor/profile.json")
    else:
        p = store.load_profile()
        for f in ("goal", "constraints", "preferences"):
            if f not in p:
                problems.append(f"档案缺少字段：{f}")
        if not p.get("goal", {}).get("statement"):
            notes.append("档案里还没有写目标（goal.statement）")

    ids = store.plan_ids()
    if not ids:
        notes.append("还没有计划")
    for pid in ids:
        plan = store.load_plan(pid)
        errors, _ = validate_plan(plan, store.load_profile() if store.has_profile() else None)
        problems += [f"[{pid}] {e}" for e in errors]

    # 日志一致性
    plan = store.load_plan() if ids else None
    if plan:
        plan_days = {d["date"]: d for d in plan["days"]}
        task_ids = {t["id"] for d in plan["days"] for t in d.get("tasks", [])}
        for e in store.load_logs():
            if e["date"] not in plan_days:
                notes.append(f"打卡记录 {e['date']} 不在当前计划周期内（历史遗留可忽略）")
            for tid in e.get("done_tasks", []):
                if tid not in task_ids:
                    problems.append(f"{e['date']} 打卡引用了不存在的任务 id：{tid}")
            for rel in e.get("evidence") or []:
                if not store.evidence_path(rel).is_file():
                    problems.append(f"{e['date']} 凭证文件缺失：{rel}")

    if problems:
        print("✗ 发现 %d 个问题：" % len(problems))
        for p in problems[:20]:
            print(f"  - {p}")
    else:
        print("✓ 数据一致性检查通过")
    for n in notes:
        print(f"  · {n}")
    return 1 if problems else 0


# ------------------------------------------------------------------ motivate / card


def cmd_motivate(args) -> int:
    store = _store(args)
    profile = store.load_profile()

    if args.show_list:
        print(motivation.listing(profile))
        return 0
    if args.reset:
        motivation.reset(store, profile)
        print("✓ 已恢复默认文案设置（自定义内容已清空）")
        return 0
    if args.on or args.off:
        cfg = dict(profile.get("motivation") or {})
        cfg["enabled"] = bool(args.on)
        profile["motivation"] = cfg
        store.save_profile(profile)
        print(f"✓ 文案已{'开启' if args.on else '关闭'}")
        return 0
    if args.mode:
        cfg = dict(profile.get("motivation") or {})
        cfg["mode"] = args.mode
        profile["motivation"] = cfg
        store.save_profile(profile)
        print(f"✓ 文案模式：{args.mode}"
              f"（mix=内置+自定义 / custom=只用自定义 / builtin=只用内置）")
        return 0
    if args.add:
        cfg = motivation.add(store, profile, args.scene, args.add)
        count = len((cfg.get("custom") or {}).get(args.scene) or [])
        print(f"✓ 已加入【{args.scene}】场景，当前自定义 {count} 条")
        print("  可用占位符：{streak} {cumulative} {percent} {days} {name}")
        return 0
    if args.remove is not None:
        removed = motivation.remove(store, profile, args.scene, args.remove)
        print(f"✓ 已删除：{removed['removed']}")
        return 0

    quote = motivation.pick(profile, args.scene, {
        "streak": 0, "cumulative": 0, "percent": 0, "days": 0,
        "name": profile.get("name", ""),
    })
    if not quote:
        print("（该场景暂无可用文案：可能已关闭，或自定义为空）")
        return 0
    print(f"「{quote}」")
    return 0


def _browser_candidates() -> list[str]:
    import shutil as sh

    cands: list[str] = []
    env = os.environ.get("CHROME_PATH")
    if env:
        cands.append(env)
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        found = sh.which(name)
        if found:
            cands.append(found)
    cands += [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        if c and c not in seen and Path(c).is_file():
            seen.add(c)
            out.append(c)
    return out


def _screenshot(html_path: Path, png_path: Path, height: int) -> bool:
    """用 headless 浏览器把 HTML 截成 PNG。找不到浏览器就返回 False。"""
    url = html_path.resolve().as_uri()
    for browser in _browser_candidates():
        cmd = [
            browser, "--headless", "--disable-gpu", "--hide-scrollbars",
            "--no-sandbox", "--disable-extensions", "--disable-dev-shm-usage",
            f"--screenshot={png_path.resolve()}",
            f"--window-size=720,{height}", url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if png_path.is_file() and png_path.stat().st_size > 2048:
            return True
    return False


def cmd_card(args) -> int:
    store, plan = _load_plan(args)
    profile = store.load_profile()
    latest = store.latest_logs_by_date()
    d = parse_date(args.date) if args.date else today()
    entry = next((x for x in plan["days"] if x["date"] == d.isoformat()), None)
    if not entry:
        raise MentorError(f"{d} 不在计划周期内（{plan['start_date']} → {plan['end_date']}）")
    log = latest.get(d.isoformat())
    stats = compute(plan, latest, ref=d, profile=profile)

    quote = args.quote
    if quote is None:
        scene = "done" if log and log.get("status") in ("done", "partial") else "low"
        quote = motivation.pick(profile, scene, {
            "streak": stats["streak"], "cumulative": stats["cumulative_days"],
            "percent": round(stats["percent"]), "days": stats["cumulative_days"],
            "name": profile.get("name", ""),
        })
    html_text = render.card_html(entry, log, plan, stats, quote or "")

    out = Path(args.out) if args.out else store.export_path(f"card-{d.isoformat()}")
    html_path = out.with_suffix(".html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_text, encoding="utf-8", newline="\n")

    if args.format == "html":
        print(f"✓ 打卡页：{html_path}")
        print("  浏览器打开后直接截图即可分享。")
        return 0

    png_path = out.with_suffix(".png")
    height = render.card_height(len(entry.get("tasks", [])),
                               bool(log and log.get("note")), bool(quote))
    if _screenshot(html_path, png_path, height):
        print(f"✓ 打卡图：{png_path}")
    else:
        print(f"! 没找到可用浏览器，已生成 HTML：{html_path}")
        print("  浏览器打开截图即可；装了 Chrome / Edge 后重跑本命令可直接出 PNG。")
    return 0


# ------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mentor",
        description="life-mentor · 人生导师模拟器：把目标拆成每天能打卡的动作",
    )
    p.add_argument("--root", help="项目根目录（默认从当前目录向上查找 .mentor）")
    sub = p.add_subparsers(dest="command", required=True)

    # init
    s = sub.add_parser("init", help="初始化档案目录")
    s.add_argument("--dir", default=".", help="项目根目录，默认当前目录")
    s.add_argument("--name")
    s.add_argument("--goal", help="一句话目标")
    s.add_argument("--tone", default="auto", choices=["auto", "strict", "gentle"])
    s.add_argument("--time-per-day", type=int, default=120, dest="time_per_day")
    s.add_argument("--checkin-time", default="21:00", dest="checkin_time")
    s.add_argument("--grace-per-week", type=int, default=1, dest="grace_per_week",
                   help="每周允许几天缺勤不打断连击，0 = 关闭宽容（默认 1）")
    s.add_argument("--max-carry-days", type=int, default=2, dest="max_carry_days",
                   help="未完成任务最多顺延几天，0 = 不顺延（默认 2）")
    s.add_argument("--force", action="store_true", help="清空旧档案重建")
    s.set_defaults(func=cmd_init)

    # profile
    s = sub.add_parser("profile", help="查看/修改用户档案")
    s.add_argument("action", choices=["show", "set"])
    s.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="点路径赋值，如 --set goal.deadline=2027-06-01")
    s.add_argument("--patch", help="用 JSON 文件做深合并")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_profile)

    # plan
    plan = sub.add_parser("plan", help="计划管理").add_subparsers(dest="action", required=True)

    s = plan.add_parser("scaffold", help="生成逐日骨架 JSON")
    s.add_argument("--goal")
    s.add_argument("--domain")
    s.add_argument("--start")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--buffer-weekday", type=int, default=6, dest="buffer_weekday",
                   help="缓冲日（0=周一 … 6=周日），默认周日")
    s.add_argument("--id")
    s.add_argument("-o", "--out")
    s.set_defaults(func=cmd_plan_scaffold)

    s = plan.add_parser("new", help="导入并校验计划")
    s.add_argument("--file", required=True)
    s.add_argument("--replace", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_plan_new)

    s = plan.add_parser("amend", help="调整 from_date 之后的计划（保留历史）")
    s.add_argument("--file", required=True)
    s.add_argument("--reason")
    s.add_argument("--force", action="store_true")
    s.add_argument("--plan-id", dest="plan_id")
    s.set_defaults(func=cmd_plan_amend)

    s = plan.add_parser("show", help="查看某天/本周/全部")
    s.add_argument("--date")
    s.add_argument("--week", action="store_true")
    s.add_argument("--all", action="store_true")
    s.add_argument("--plan-id", dest="plan_id")
    s.set_defaults(func=cmd_plan_show)

    s = plan.add_parser("list", help="列出所有计划与版本历史")
    s.set_defaults(func=cmd_plan_list)

    # checkin
    s = sub.add_parser("checkin", help="每日打卡")
    s.add_argument("--status", default="done", choices=["done", "partial", "skip", "blocked"])
    s.add_argument("--tasks", help="完成的任务 id，逗号分隔；done 默认全选")
    s.add_argument("--note")
    s.add_argument("--date")
    s.add_argument("--energy", type=int, choices=[1, 2, 3, 4, 5], help="当天精力 1-5")
    s.add_argument("--evidence", action="append", metavar="PATH",
                   help="打卡凭证文件（图片/文件），可重复传或逗号分隔")
    s.add_argument("--plan-id", dest="plan_id")
    s.set_defaults(func=cmd_checkin)

    # status
    s = sub.add_parser("status", help="总览：进度、今日任务、连续天数")
    s.add_argument("--json", action="store_true")
    s.add_argument("--plan-id", dest="plan_id")
    s.set_defaults(func=cmd_status)

    # review
    s = sub.add_parser("review", help="生成周复盘")
    s.add_argument("--week", help="如 2026-W47，默认本周")
    s.add_argument("--json", action="store_true")
    s.add_argument("--plan-id", dest="plan_id")
    s.set_defaults(func=cmd_review)

    # export
    s = sub.add_parser("export", help="导出 Markdown / ICS")
    s.add_argument("--format", default="md", choices=["md", "ics"])
    s.add_argument("--pending", action="store_true", help="ics 只导出未完成任务")
    s.add_argument("-o", "--out")
    s.add_argument("--plan-id", dest="plan_id")
    s.set_defaults(func=cmd_export)

    # motivate
    s = sub.add_parser("motivate", help="查看/自定义激励文案")
    s.add_argument("--scene", default="done", choices=list(motivation.SCENES))
    s.add_argument("--list", action="store_true", dest="show_list", help="列出当前所有文案")
    s.add_argument("--add", metavar="TEXT", help="追加一条自定义文案")
    s.add_argument("--remove", type=int, metavar="N", help="删除指定序号的自定义文案")
    s.add_argument("--reset", action="store_true", help="恢复默认（清空自定义）")
    s.add_argument("--mode", choices=["mix", "custom", "builtin"],
                   help="mix=内置+自定义 / custom=只用自定义 / builtin=只用内置")
    s.add_argument("--on", action="store_true", help="开启文案")
    s.add_argument("--off", action="store_true", help="关闭文案")
    s.set_defaults(func=cmd_motivate)

    # card
    s = sub.add_parser("card", help="生成当天打卡图（PNG/HTML）")
    s.add_argument("--date")
    s.add_argument("--out", help="输出路径（不含扩展名）")
    s.add_argument("--format", default="png", choices=["png", "html"])
    s.add_argument("--quote", help="卡片底部自定义那句话")
    s.add_argument("--plan-id", dest="plan_id")
    s.set_defaults(func=cmd_card)

    # doctor
    s = sub.add_parser("doctor", help="数据一致性自检")
    s.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except MentorError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"✗ 文件不存在：{exc.filename}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
