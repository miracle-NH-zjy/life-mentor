#!/usr/bin/env python3
"""文案层：打卡、恢复、里程碑、低谷四个场景的激励语。

设计约束：
· 内置文案必须有信息，不能是「加油你一定行」这类空话
· 用户可通过 `mentor.py motivate --add` 追加，或在 profile 里整组替换
· 同一场景短期不重复（记录最近用过的，从候选里剔除）
· 支持占位符 {days} {streak} {rate} {name}，渲染时替换
"""

from __future__ import annotations

import random
from typing import Any

from .store import MentorError, now_iso, read_json, write_json

SCENES = ("done", "recovery", "milestone", "low", "blocked", "skip")

SCENE_LABEL = {
    "done": "打卡完成",
    "recovery": "断签后恢复",
    "milestone": "里程碑",
    "low": "低谷",
    "blocked": "受阻",
    "skip": "主动休息",
}

BUILTIN: dict[str, list[str]] = {
    "done": [
        "做完了。今天这一格是真的。",
        "完成本身就是证据——证明这件事在你的掌控里。",
        "不需要感动，记下来就行。{streak} 天了。",
        "今天的进度条往前挪了一点，这就够了。",
        "做完比做完美重要。你今天赢了这一回合。",
        "这一项进了账，它不会因为你某天没做而消失。",
        "记下来了。明天的事明天再说。",
        "你今天没有和自己讨价还价——这比任务本身更难。",
    ],
    "recovery": [
        "断了几天，又回来了。回来这件事比从不中断更稀有。",
        "重新开始不需要仪式。你刚才就已经开始了。",
        "中断过的人才知道怎么接着往下走。今天的 {streak} 天算数。",
        "之前的记录还在，没有作废。你不是从零开始，是从 {cumulative} 继续。",
        "断一次不等于失败，断完不回来才算。你回来了。",
    ],
    "milestone": [
        "{cumulative} 天了。这个数字本身没有魔力，但它说明你能稳定地做一件事。",
        "已经走了 {percent}% 的路。回头看，这段时间你没在原地打转。",
        "连续 {streak} 天——不是靠意志力，是靠你已经把它变成了日常。",
        "{cumulative} 天。当初那个「我大概坚持不下来」的判断，正在被推翻。",
    ],
    "low": [
        "完成率低不代表你不行，只代表这个计划定得比现实重。该调的是计划。",
        "今天没做到，不代表明天也做不到。这两件事之间没有因果关系。",
        "现在的数字不好看，但它至少是真实的。真实的数字才能改。",
        "先别谈坚持，先谈能不能明天打开它一次。",
        "你在硬扛一个不匹配的计划。这不是你的错，但改变它是你的责任。",
    ],
    "blocked": [
        "被挡住了就记下来，这比硬撑有用。原因写清楚，下一版计划才有依据。",
        "受阻不是断签。你已经如实上报了，这就是在做正确的事。",
        "环境不配合的时候，改环境，别改自己。",
    ],
    "skip": [
        "主动休息也是计划的一部分。你今天做了选择，不是逃避。",
        "停下来一天不会让前面的努力消失，连续 {streak} 天还在。",
        "会休息的人才跑得远。明天见。",
    ],
}

DEFAULTS = {"enabled": True, "mode": "mix", "custom": {}, "recent": 4}


# ------------------------------------------------------------------ 配置


def _config(profile: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    cfg.update(profile.get("motivation") or {})
    return cfg


def candidates(profile: dict[str, Any], scene: str) -> list[str]:
    """mix = 内置 + 自定义；custom = 只用自定义；builtin = 只用内置。"""
    cfg = _config(profile)
    custom = (cfg.get("custom") or {}).get(scene) or []
    mode = cfg.get("mode", "mix")
    if mode == "custom":
        return list(custom)
    if mode == "builtin":
        return list(BUILTIN.get(scene, []))
    return list(BUILTIN.get(scene, [])) + list(custom)


def render_text(template: str, ctx: dict[str, Any]) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def pick(profile: dict[str, Any], scene: str, ctx: dict[str, Any],
         exclude: list[str] | None = None) -> str:
    cfg = _config(profile)
    if not cfg.get("enabled", True):
        return ""
    pool = candidates(profile, scene)
    if not pool:
        return ""
    avoid = set(exclude or []) | set(cfg.get("recent_log") or [])
    fresh = [t for t in pool if t not in avoid]
    chosen = random.choice(fresh or pool)
    return render_text(chosen, ctx)


def remember(store, text: str) -> None:
    """记录最近用过的文案，避免短期内重复。"""
    path = store.base / ".motivation_state.json"
    state = {}
    if path.is_file():
        try:
            state = read_json(path)
        except MentorError:
            state = {}
    recent = state.get("recent", [])
    recent.append(text)
    state["recent"] = recent[-6:]
    state["updated_at"] = now_iso()
    write_json(path, state)


# ------------------------------------------------------------------ 命令支持


def add(store, profile: dict[str, Any], scene: str, text: str) -> dict[str, Any]:
    if scene not in SCENES:
        raise MentorError(f"未知场景：{scene}（可选：{', '.join(SCENES)}）")
    cfg = _config(profile)
    custom = dict(cfg.get("custom") or {})
    items = list(custom.get(scene) or [])
    if text in items:
        raise MentorError("这条文案已经存在了")
    items.append(text)
    custom[scene] = items
    cfg["custom"] = custom
    profile["motivation"] = cfg
    store.save_profile(profile)
    return cfg


def remove(store, profile: dict[str, Any], scene: str, index: int) -> dict[str, Any]:
    cfg = _config(profile)
    custom = dict(cfg.get("custom") or {})
    items = list(custom.get(scene) or [])
    if not 1 <= index <= len(items):
        raise MentorError(f"序号超出范围：{scene} 只有 {len(items)} 条自定义文案")
    removed = items.pop(index - 1)
    custom[scene] = items
    cfg["custom"] = custom
    profile["motivation"] = cfg
    store.save_profile(profile)
    return {"removed": removed, "cfg": cfg}


def reset(store, profile: dict[str, Any]) -> None:
    profile["motivation"] = dict(DEFAULTS)
    store.save_profile(profile)


def listing(profile: dict[str, Any]) -> str:
    cfg = _config(profile)
    lines = [f"模式：{cfg.get('mode')}   启用：{cfg.get('enabled')}"]
    for scene in SCENES:
        builtin = BUILTIN.get(scene, [])
        custom = (cfg.get("custom") or {}).get(scene) or []
        lines.append(f"\n【{scene}】{SCENE_LABEL[scene]}  内置 {len(builtin)} 条 / 自定义 {len(custom)} 条")
        for i, t in enumerate(custom, 1):
            lines.append(f"  {i}. {t}")
    return "\n".join(lines)
