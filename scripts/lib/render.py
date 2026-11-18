#!/usr/bin/env python3
"""渲染层：终端视图 + Markdown 导出。纯标准库，中文按双宽处理对齐。"""

from __future__ import annotations

import unicodedata
from datetime import date
from typing import Any

from .cal import day_index, parse_date, phase_for, weekday_cn

STATUS_LABEL = {
    "done": "完成",
    "partial": "部分完成",
    "skip": "主动跳过",
    "blocked": "受阻",
    "missing": "未打卡",
}


# ------------------------------------------------------------------ 对齐工具


def dwidth(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def pad(text: str, width: int, align: str = "left") -> str:
    gap = max(0, width - dwidth(text))
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def truncate(text: str, width: int) -> str:
    if dwidth(text) <= width:
        return text
    out, used = [], 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if used + w > width - 1:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


def bar(ratio: float, width: int = 20) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


def hr(width: int = 62, ch: str = "─") -> str:
    return ch * width


# ------------------------------------------------------------------ 视图


def day_card(entry: dict, log: dict | None, plan: dict, *, show_verify: bool = True) -> str:
    d = parse_date(entry["date"])
    total = len(plan.get("days", []))
    idx = day_index(d, parse_date(plan["start_date"]))
    phase = entry.get("phase") or phase_for(d, plan.get("phases", []))
    buffer_tag = " · 缓冲日" if entry.get("is_buffer") else ""
    head = f"{entry['date']} {weekday_cn(d)} · 第 {idx}/{total} 天 · {phase}{buffer_tag}"

    lines = [head, hr(dwidth(head))]
    tasks = entry.get("tasks", [])
    if not tasks:
        lines.append("  （无任务，休息）")
    done_ids = set((log or {}).get("done_tasks", []))
    st = (log or {}).get("status", "missing")
    for i, t in enumerate(tasks, 1):
        mark = "✓" if t.get("id") in done_ids else ("·" if st == "missing" else "✗")
        title = truncate(t.get("title", ""), 42)
        lines.append(f" {mark} {i}. {pad(title, 44)}{pad(str(t.get('est_min', '')) + 'min', 7, 'right')}")
        if show_verify and t.get("verify"):
            lines.append(f"     验收：{t['verify']}")
    if log and log.get("note"):
        lines.append(f"  备注：{log['note']}")
    if log:
        lines.append(f"  状态：{STATUS_LABEL.get(st, st)}")
    return "\n".join(lines)


def status_view(stats: dict, plan: dict) -> str:
    out: list[str] = []
    out.append("人生导师 · 计划总览")
    out.append(hr(62, "═"))
    out.append(f"目标：{stats['goal']}")
    out.append(f"周期：{stats['start_date']} → {stats['end_date']}"
               f"（计划 v{stats['version']}，共 {stats['total_days']} 天）")
    out.append(f"进度：[{bar(stats['percent'] / 100)}] {stats['percent']}%"
               f"  已过 {stats['elapsed_days']} 天 / 剩 {stats['remaining_days']} 天")

    entry = stats.get("today_entry")
    if entry:
        out.append("")
        out.append(day_card(entry, stats.get("today_log"), plan))
    elif not stats.get("in_range"):
        out.append("")
        out.append(f"⚠ 今天（{stats['today']}）不在计划周期内。")
    else:
        out.append("")
        out.append(f"今天（{stats['today']}）计划里没有条目。")

    out.append("")
    out.append(hr())
    out.append(
        f"数据 · 日均完成率 {round(stats['day_rate'] * 100)}%"
        f" | 任务完成 {stats['done_tasks']}/{stats['total_tasks']}"
        f" | 连续打卡 {stats['streak']} 天（最佳 {stats['best_streak']}）"
    )
    if stats["missing_dates"]:
        out.append(f"漏打卡 {len(stats['missing_dates'])} 天"
                   f"（最近：{stats['missing_dates'][-1]}）")
    if stats["blocked_dates"]:
        out.append(f"受阻 {len(stats['blocked_dates'])} 天"
                   f"（最近：{stats['blocked_dates'][-1]}）")
    if stats["by_phase"]:
        out.append("")
        out.append("分阶段：")
        for name, b in stats["by_phase"].items():
            rate = b["score"] / b["days"] if b["days"] else 0
            out.append(f"  {pad(truncate(name, 24), 26)}[{bar(rate, 12)}] {round(rate * 100)}%")

    out.append("")
    out.append(hr())
    if stats["needs_adapt"]:
        out.append("⚠ 已过去 7 天以上但日均完成率低于 50% —— 计划与你的实际承载力不匹配，")
        out.append("  建议执行 plan amend 下调强度，而不是硬扛。")
    elif entry and stats["today_pending_tasks"]:
        out.append(f"→ 今天还剩 {len(stats['today_pending_tasks'])} 项。完成后运行：")
        out.append("  python scripts/mentor.py checkin --status done")
    elif stats.get("today_log"):
        out.append("→ 今天已打卡。明天见。")
    else:
        out.append("→ 今天还没打卡：python scripts/mentor.py checkin --status done")
    return "\n".join(out)


def week_view(ws: dict, plan: dict) -> str:
    out = [f"本周 {ws['week']} · 计划 {ws['planned_days']} 天 / 已过 {ws.get('settled_days', 0)} 天"
           f" / 打卡 {ws['logged_days']} 天 / 完成度 {round(ws['score'] * 100)}%", hr()]
    for row in ws["rows"]:
        d = parse_date(row["date"])
        st = (row["log"] or {}).get("status", "missing")
        mark = {"done": "✓", "partial": "◐", "skip": "○", "blocked": "✗"}.get(st, "·")
        title = ""
        if row["plan"]:
            titles = [t.get("title", "") for t in row["plan"].get("tasks", [])]
            title = truncate(" / ".join(titles) if titles else "（无任务）", 40)
        out.append(f" {mark} {row['date'][5:]} {pad(weekday_cn(d), 5)}{pad(title, 42)}"
                   f"{STATUS_LABEL.get(st, st) if row['log'] else ''}")
    return "\n".join(out)


def plan_markdown(plan: dict, latest_logs: dict[str, dict]) -> str:
    """导出完整计划为 Markdown 表格，可读、可 diff、可贴到任何地方。"""
    lines = [
        f"# {plan['goal']}",
        "",
        f"- 计划 ID：`{plan['id']}`（v{plan.get('version', 1)}）",
        f"- 领域：{plan.get('domain') or '未指定'}",
        f"- 周期：{plan['start_date']} → {plan['end_date']}，共 {len(plan.get('days', []))} 天",
        "",
    ]
    if plan.get("phases"):
        lines.append("## 阶段")
        lines.append("")
        lines.append("| 阶段 | 起止 | 重心 |")
        lines.append("| --- | --- | --- |")
        for ph in plan["phases"]:
            lines.append(f"| {ph['name']} | {ph['start']} ~ {ph['end']} | {ph.get('focus', '')} |")
        lines.append("")

    lines.append("## 逐日计划")
    lines.append("")
    lines.append("| 日期 | 星期 | 任务 | 当日验收 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for entry in plan.get("days", []):
        d = parse_date(entry["date"])
        log = latest_logs.get(entry["date"])
        st = STATUS_LABEL.get((log or {}).get("status", "missing"), "未打卡")
        tasks = entry.get("tasks", [])
        task_txt = "<br>".join(
            f"{i}. {t['title']}（{t.get('est_min', '?')}min）" for i, t in enumerate(tasks, 1)
        ) or "休息"
        verify_txt = "<br>".join(f"{i}. {t.get('verify', '')}" for i, t in enumerate(tasks, 1)) or "—"
        tag = "缓冲日" if entry.get("is_buffer") else ""
        wd = weekday_cn(d) + (f" {tag}" if tag else "")
        lines.append(f"| {entry['date']} | {wd} | {task_txt} | {verify_txt} | {st} |")
    return "\n".join(lines) + "\n"


def review_markdown(stats: dict, ws: dict, plan: dict) -> str:
    """脚本产出事实，归因与调整留给 LLM 填。"""
    lines = [
        f"# 复盘 · {ws['week']}",
        "",
        "## 事实（机器统计，不要改写）",
        "",
        f"- 计划完成度：{round(ws['score'] * 100)}%（本周 {ws['planned_days']} 个计划日，已结束 {ws.get('settled_days', 0)} 天，打卡 {ws['logged_days']} 天）",
        f"- 全周期日均完成率：{round(stats['day_rate'] * 100)}%",
        f"- 连续打卡：{stats['streak']} 天（历史最佳 {stats['best_streak']} 天）",
        f"- 受阻天数：{len(stats['blocked_dates'])}；跳过：{len(stats['skipped_dates'])}；漏打卡：{len(stats['missing_dates'])}",
        "",
        "### 本周逐日",
        "",
        "| 日期 | 星期 | 任务 | 状态 | 备注 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in ws["rows"]:
        d = parse_date(row["date"])
        if d > date.today():
            st = "—"  # 还没到的日子不判定
        else:
            st = STATUS_LABEL.get((row["log"] or {}).get("status", "missing"), "未打卡")
        titles = ""
        if row["plan"]:
            titles = " / ".join(t.get("title", "") for t in row["plan"].get("tasks", [])) or "休息"
        note = (row["log"] or {}).get("note", "")
        lines.append(f"| {row['date']} | {weekday_cn(d)} | {titles} | {st} | {note} |")

    lines += [
        "",
        "## 归因（待填写）",
        "",
        "> 写出本周真正的卡点：是时间不够、任务估算错了、还是动机不足？",
        "> 只写可验证的原因，不写「不够努力」这种无法反驳也没法改的话。",
        "",
        "- 卡点 1：",
        "- 卡点 2：",
        "",
        "## 调整（待填写）",
        "",
        "- [ ] 保留什么：",
        "- [ ] 砍掉什么：",
        "- [ ] 下周改什么：",
    ]
    if stats["needs_adapt"]:
        lines += [
            "",
            "## ⚠ 系统判断",
            "",
            "日均完成率低于 50% 且已过 7 天以上。这不是意志力问题，是计划强度与承载力不匹配。",
            "下一步应执行 `plan amend` 下调任务量，而不是加码。",
        ]
    return "\n".join(lines) + "\n"
