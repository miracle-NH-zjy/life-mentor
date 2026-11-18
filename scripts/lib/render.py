#!/usr/bin/env python3
"""渲染层：终端视图 + Markdown 导出。纯标准库，中文按双宽处理对齐。"""

from __future__ import annotations

import html
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
    if log and log.get("evidence"):
        names = [e.rsplit("/", 1)[-1] for e in log["evidence"]]
        lines.append(f"  凭证：{len(names)} 个 · {', '.join(truncate(n, 20) for n in names)}")
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

    carry = stats.get("carryover") or []
    if carry:
        out.append("")
        out.append(f"待补（{len(carry)} 项，未完成不顺延作废）")
        for item in carry:
            left = item["expires_in"]
            tag = "今天最后一天" if left == 0 else f"还剩 {left} 天"
            out.append(f"  ← {pad(item['from_date'][5:], 6)}{truncate(item['task'].get('title', ''), 34)}"
                       f"{pad(item['task'].get('est_min', '') and str(item['task']['est_min']) + 'min' or '', 7, 'right')}"
                       f"  {tag}")

    out.append("")
    out.append(hr())
    out.append(
        f"数据 · 累计 {stats.get('cumulative_days', 0)} 天"
        f"（有效 {stats.get('effective_days', 0)}）"
        f" | 当前连击 {stats['streak']} 天（最佳 {stats['best_streak']}）"
        f" | 日均完成率 {round(stats['day_rate'] * 100)}%"
    )
    if stats.get("grace_per_week"):
        used = stats["week"] in (stats.get("grace_weeks_used") or [])
        out.append(f"宽容 · 每周 {stats['grace_per_week']} 次缺勤豁免"
                   f"{'（本周已用）' if used else '（本周可用）'}"
                   f" · 累计天数永不归零")
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


# ------------------------------------------------------------------ 打卡卡片

CARD_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{width:720px;background:#eef0f4;padding:28px;
     font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
     -webkit-font-smoothing:antialiased}
.card{background:#fff;border-radius:18px;padding:34px 38px 26px;
      box-shadow:0 10px 30px rgba(17,24,39,.07)}
.top{display:flex;align-items:baseline;justify-content:space-between;
     padding-bottom:16px;border-bottom:1px solid #eef0f4}
.date{font-size:30px;font-weight:700;color:#111827;letter-spacing:-.4px}
.date .wd{font-size:17px;font-weight:500;color:#9ca3af;margin-left:10px}
.idx{font-size:14px;font-weight:600;color:#2563eb;background:#eff4ff;
     padding:5px 11px;border-radius:20px}
.goal{font-size:14px;color:#6b7280;line-height:1.6;margin-top:16px}
.phase{display:inline-block;font-size:12px;color:#7c3aed;background:#f5f0ff;
       padding:3px 9px;border-radius:6px;margin-top:10px;font-weight:600}
.tasks{list-style:none;margin:20px 0 4px}
.tasks li{display:flex;align-items:flex-start;gap:12px;padding:11px 0;
          border-bottom:1px dashed #f0f1f4}
.tasks li:last-child{border-bottom:none}
.box{width:21px;height:21px;border-radius:7px;flex-shrink:0;margin-top:2px;
     display:flex;align-items:center;justify-content:center;
     font-size:13px;font-weight:700;border:1.5px solid #d8dbe2;color:transparent}
li.done .box{background:#059669;border-color:#059669;color:#fff}
li.part .box{background:#f59e0b;border-color:#f59e0b;color:#fff}
.t{font-size:15.5px;color:#111827;line-height:1.45;font-weight:500}
li.done .t{color:#6b7280;text-decoration:line-through;text-decoration-color:#cbd5e1}
.v{font-size:12.5px;color:#9ca3af;margin-top:3px;line-height:1.5}
.m{font-size:12.5px;color:#b0b5bf;flex-shrink:0;margin-top:3px;font-variant-numeric:tabular-nums}
.stats{display:flex;gap:8px;margin-top:20px;padding:16px 0;
       border-top:1px solid #eef0f4;border-bottom:1px solid #eef0f4}
.stats div{flex:1;text-align:center}
.stats b{display:block;font-size:23px;font-weight:700;color:#111827;
         font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.stats span{font-size:11.5px;color:#9ca3af;display:block;margin-top:3px}
.quote{margin-top:18px;font-size:13.5px;color:#4b5563;line-height:1.7;
       padding-left:12px;border-left:3px solid #dbeafe}
.foot{margin-top:16px;display:flex;justify-content:space-between;
      font-size:11px;color:#c9ccd4}
"""


def card_html(entry: dict, log: dict | None, plan: dict, stats: dict,
              quote: str = "") -> str:
    """生成一张自包含的打卡卡片，用于转 PNG 或直接在浏览器里截图。"""
    d = parse_date(entry["date"])
    total = len(plan.get("days", []))
    idx = day_index(d, parse_date(plan["start_date"]))
    phase = entry.get("phase") or phase_for(d, plan.get("phases", []))
    st = (log or {}).get("status", "missing")
    done_ids = set((log or {}).get("done_tasks", []))
    tasks = entry.get("tasks", [])

    rows = []
    for t in tasks:
        cls = "done" if t.get("id") in done_ids else ("part" if st == "partial" else "")
        mark = "✓" if t.get("id") in done_ids else ""
        rows.append(
            f'<li class="{cls}"><span class="box">{mark}</span>'
            f'<div style="flex:1"><div class="t">{html.escape(t.get("title", ""))}</div>'
            f'<div class="v">{html.escape(t.get("verify", ""))}</div></div>'
            f'<span class="m">{t.get("est_min", "")}min</span></li>'
        )
    if not rows:
        rows.append('<li><span class="box"></span><div style="flex:1">'
                    '<div class="t">今天没有任务</div>'
                    '<div class="v">缓冲日：只补欠账，不排新任务</div></div></li>')

    q = f'<div class="quote">{html.escape(quote)}</div>' if quote else ""
    note = ""
    if log and log.get("note"):
        note = f'<div class="quote">备注：{html.escape(log["note"])}</div>'
    ev = ""
    if log and log.get("evidence"):
        ev = f'<div class="foot" style="margin-top:8px">已附凭证 {len(log["evidence"])} 个</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{d.isoformat()} 打卡</title><style>{CARD_CSS}</style></head>
<body><div class="card">
<div class="top">
  <div class="date">{d.month} 月 {d.day} 日<span class="wd">{weekday_cn(d)}</span></div>
  <div class="idx">第 {idx} / {total} 天</div>
</div>
<div class="goal">{html.escape(plan.get("goal", ""))}</div>
<div class="phase">{html.escape(phase)}</div>
<ul class="tasks">{"".join(rows)}</ul>
<div class="stats">
  <div><b>{stats.get("cumulative_days", 0)}</b><span>累计天数</span></div>
  <div><b>{stats.get("streak", 0)}</b><span>连续打卡</span></div>
  <div><b>{round(stats.get("day_rate", 0) * 100)}%</b><span>日均完成率</span></div>
</div>
{note}{q}{ev}
<div class="foot"><span>{STATUS_LABEL.get(st, "未打卡")}</span><span>life-mentor</span></div>
</div></body></html>
"""


def card_height(task_count: int, has_note: bool = False, has_quote: bool = False) -> int:
    """估算卡片像素高度，供 headless 浏览器截图时设置窗口。"""
    h = 250 + max(1, task_count) * 78 + 130
    h += 60 if has_note else 0
    h += 70 if has_quote else 0
    return h
