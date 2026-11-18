#!/usr/bin/env python3
"""状态层：.mentor 目录的读写。

设计约束：
1. 所有写入必须是原子写（temp + os.replace），避免断电/异常导致 JSON 半截。
2. 打卡走 append-only JSONL，任何一行损坏都不影响其它历史。
3. 计划每次保存都归档旧版本，历史不可覆写。
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT_DIRNAME = ".mentor"
PROFILE_FILE = "profile.json"


class MentorError(Exception):
    """用户可读的业务错误，CLI 捕获后直接打印，不带 traceback。"""


# ------------------------------------------------------------------ 基础 IO


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def today() -> date:
    return date.today()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise MentorError(f"文件不存在：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MentorError(f"JSON 解析失败：{path} -> {exc}") from exc


def write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# ------------------------------------------------------------------ 定位


def find_project_root(start: Path | str | None = None) -> Path:
    """从 start（默认 cwd）向上查找 .mentor 目录。"""
    here = Path(start).resolve() if start else Path.cwd().resolve()
    for cand in (here, *here.parents):
        if (cand / ROOT_DIRNAME).is_dir():
            return cand
    raise MentorError(
        f"未找到 {ROOT_DIRNAME}/ 目录。\n"
        f"  当前目录：{here}\n"
        f"  请先在项目根目录运行：python scripts/mentor.py init"
    )


# ------------------------------------------------------------------ Store


class Store:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.base = self.root / ROOT_DIRNAME
        self.plans_dir = self.base / "plans"
        self.archive_dir = self.plans_dir / "archive"
        self.logs_dir = self.base / "logs"
        self.reviews_dir = self.base / "reviews"
        self.exports_dir = self.base / "exports"
        self.evidence_dir = self.base / "evidence"

    # ---- 构造

    @classmethod
    def create(cls, root: Path | str, force: bool = False) -> "Store":
        store = cls(root)
        if store.base.exists() and not force:
            raise MentorError(
                f"{store.base} 已存在。若确认要重建请加 --force（会清空旧档案）。"
            )
        if store.base.exists() and force:
            shutil.rmtree(store.base)
        for d in (store.plans_dir, store.archive_dir, store.logs_dir,
                  store.reviews_dir, store.exports_dir, store.evidence_dir):
            d.mkdir(parents=True, exist_ok=True)
        return store

    @classmethod
    def open(cls, root: Path | str | None = None) -> "Store":
        return cls(find_project_root(root))

    # ---- profile

    @property
    def profile_path(self) -> Path:
        return self.base / PROFILE_FILE

    def has_profile(self) -> bool:
        return self.profile_path.is_file()

    def load_profile(self) -> dict[str, Any]:
        if not self.has_profile():
            raise MentorError("档案不存在。先运行：python scripts/mentor.py init")
        return read_json(self.profile_path)

    def save_profile(self, profile: dict[str, Any]) -> None:
        profile["updated_at"] = now_iso()
        write_json(self.profile_path, profile)

    # ---- plans

    def plan_path(self, plan_id: str) -> Path:
        return self.plans_dir / f"{plan_id}.json"

    def plan_ids(self) -> list[str]:
        return sorted(p.stem for p in self.plans_dir.glob("*.json"))

    def load_plan(self, plan_id: str | None = None) -> dict[str, Any]:
        if plan_id:
            path = self.plan_path(plan_id)
            if not path.is_file():
                available = ", ".join(self.plan_ids()) or "无"
                raise MentorError(f"计划不存在：{plan_id}（现有：{available}）")
            return read_json(path)

        candidates = [read_json(p) for p in self.plans_dir.glob("*.json")]
        active = [c for c in candidates if c.get("status") == "active"]
        if not active:
            raise MentorError(
                "没有进行中的计划。先运行 plan scaffold 生成骨架，再用 plan new 导入。"
            )
        return max(active, key=lambda c: c.get("updated_at", ""))

    def save_plan(self, plan: dict[str, Any], action: str = "update") -> Path:
        """保存计划，旧版本自动归档到 plans/archive/。"""
        plan_id = plan["id"]
        path = self.plan_path(plan_id)
        if path.is_file():
            old = read_json(path)
            old_version = int(old.get("version", 1))
            write_json(self.archive_dir / f"{plan_id}.v{old_version}.json", old)
            plan["version"] = old_version + 1
        else:
            plan["version"] = max(1, int(plan.get("version") or 0))

        plan["updated_at"] = now_iso()
        history = plan.setdefault("history", [])
        history.append(
            {"version": plan["version"], "at": plan["updated_at"], "action": action}
        )
        write_json(path, plan)
        return path

    # ---- logs（append-only）

    def log_path(self, d: date) -> Path:
        return self.logs_dir / f"{d:%Y-%m}.jsonl"

    def append_log(self, entry: dict[str, Any]) -> None:
        d = date.fromisoformat(entry["date"])
        path = self.log_path(d)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_logs(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for p in sorted(self.logs_dir.glob("*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # 单行损坏不拖垮整段历史
        return sorted(entries, key=lambda e: (e.get("date", ""), e.get("at", "")))

    def latest_logs_by_date(self) -> dict[str, dict[str, Any]]:
        """同一天多次打卡时，以最后一次为准。"""
        latest: dict[str, dict[str, Any]] = {}
        for e in self.load_logs():
            latest[e["date"]] = e
        return latest

    # ---- 打卡凭证

    def save_evidence(self, src: Path | str, d: date) -> str:
        """把凭证文件复制进 .mentor/evidence/YYYY-MM/，返回相对 .mentor 的路径。"""
        path = Path(src).expanduser()
        if not path.is_file():
            raise MentorError(f"凭证文件不存在：{path}")
        target_dir = self.evidence_dir / f"{d:%Y-%m}"
        target_dir.mkdir(parents=True, exist_ok=True)
        stem, suffix = path.stem, path.suffix.lower()
        candidate = target_dir / f"{d:%Y-%m-%d}_{stem}{suffix}"
        n = 1
        while candidate.exists():
            candidate = target_dir / f"{d:%Y-%m-%d}_{stem}_{n}{suffix}"
            n += 1
        shutil.copy2(path, candidate)
        return str(candidate.relative_to(self.base)).replace("\\", "/")

    def evidence_path(self, rel: str) -> Path:
        """把记录里的相对路径还原成绝对路径（用于校验是否真的存在）。"""
        return self.base / rel.replace("/", os.sep)

    # ---- 其它

    def save_review(self, week: str, text: str) -> Path:
        path = self.reviews_dir / f"{week}.md"
        atomic_write(path, text)
        return path

    def export_path(self, name: str) -> Path:
        return self.exports_dir / name
