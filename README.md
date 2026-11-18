# life-mentor · 人生导师模拟器

> 把「我想变好」压成一份**每天打开就能打勾**的清单。

一个给 AI Agent 用的 Skill：你讲清自己的经历和想要什么，它先诊断，再生成精确到每一天、每天带验收标准的计划，之后每天打卡、每周复盘、按实际情况调整。

不是待办清单，不是鸡汤生成器。它更像一个会盯着你、也敢告诉你「这个目标不现实」的教练。

```
$ mentor status

人生导师 · 计划总览
══════════════════════════════════════════════════════════════
目标：30 天内让蓝桥杯嵌入式省赛的每个模块都能独立跑通
周期：2026-11-09 → 2026-12-08（计划 v2，共 30 天）
进度：[███████░░░░░░░░░░░░░] 33.3%  已过 10 天 / 剩 20 天

2026-11-18 周三 · 第 10/30 天 · P2 外设拆解
───────────────────────────────────────────
 · 1. 外部中断 + 旋转编码器读方向                   75min
     验收：正反转计数与实际一致，快速旋转不丢步

──────────────────────────────────────────────────────────────
数据 · 日均完成率 83% | 任务完成 10/32 | 连续打卡 1 天（最佳 7）
受阻 1 天（最近：2026-11-16）

分阶段：
  P1 打通工具链             [███████████░] 93%
  P2 外设拆解               [██████░░░░░░] 50%
```

---

## 它要解决的问题

大多数「目标管理」失败，不是因为不够努力，是因为三件事：

1. **目标是愿望，不是计划。**「我要学好英语」和「今晚 20:00 背 30 个词并各造一句」之间隔着一整套拆解工作，而没人教怎么拆。
2. **计划强度超过真实承载力。** 按理想状态排 6 小时，实际只能投入 1 小时，第三天就崩，然后彻底放弃。
3. **中断一次就归零。** 没有缓冲机制，断签等于失败，失败等于重启，重启等于又从零开始。

life-mentor 针对这三点设计：**先访谈再计划**、**任务必须可验收**、**完成率低就降强度而不是加码**。

---

## 它和普通待办 / 打卡 App 的区别

| | 普通待办 | 打卡 App | life-mentor |
|---|---|---|---|
| 谁拆解目标 | 你自己 | 你自己 | AI 访谈后拆，且受硬约束校验 |
| 任务定义 | 一句话 | 一句话 | 标题 + 时长 + **可验收的证据** |
| 计划错了怎么办 | 自己改 | 自己改 | 复盘归因 → 生成新版本，旧版本留档 |
| 断签之后 | 数据归零 | 数据归零 | 缓冲日吸收，连续天数从昨天续算 |
| 数据归属 | 平台 | 平台 | 本地 `.mentor/` 目录，可 git 追踪 |

---

## 快速开始

需要 Python 3.9+，**零第三方依赖**。

```bash
git clone https://github.com/<you>/life-mentor.git
cd life-mentor

# 1) 建立档案
python scripts/mentor.py init --dir . --name 小林 --goal "30 天拿下嵌入式基础模块"

# 2) 生成 30 天骨架（日期由脚本算，不要自己算）
python scripts/mentor.py plan scaffold --start 2026-11-18 --days 30 -o plan.json

# 3) 填完 plan.json 的 phases 和 tasks 后导入（会校验）
python scripts/mentor.py plan new --file plan.json

# 4) 每天打卡
python scripts/mentor.py checkin --status done

# 5) 看进度 / 每周复盘
python scripts/mentor.py status
python scripts/mentor.py review
```

---

## 命令一览

| 目的 | 命令 |
|---|---|
| 初始化档案 | `mentor.py init --dir . --name 小林 --goal "..."` |
| 查看/修改档案 | `mentor.py profile show`<br>`mentor.py profile set --set constraints.time_per_day_min=90` |
| 生成逐日骨架 | `mentor.py plan scaffold --start 2026-11-18 --days 30 -o plan.json` |
| 导入并校验 | `mentor.py plan new --file plan.json` |
| 看今天 / 本周 / 全部 | `mentor.py plan show` / `--week` / `--all` |
| 打卡 | `mentor.py checkin --status done\|partial\|skip\|blocked` |
| 进度总览 | `mentor.py status`（`--json` 给机器读） |
| 周复盘 | `mentor.py review`（`--week 2026-W47`） |
| 调整计划 | `mentor.py plan amend --file patch.json --reason "..."` |
| 导出 | `mentor.py export --format md\|ics --pending` |
| 数据自检 | `mentor.py doctor` |

打卡的四种状态：`done` 全部完成 / `partial` 部分完成（要指定 task id）/ `skip` 主动跳过 / `blocked` 被外部原因挡住（**必须写清原因**，这是调计划最重要的原料）。

---

## 工作流程

```
访谈（3 轮）
   ↓
诊断（真实起点 · 硬约束 · 目标判定 · 关键杠杆 · 最大风险）
   ↓
生成骨架 → 填内容 → 校验 → 落盘
   ↓
每天打卡 ←──────────────┐
   ↓                    │
每周复盘 → 归因 → 调整计划 ┘
```

关键分工：**AI 负责诊断、判断、写内容；脚本负责所有日期算术和状态一致性。**
让语言模型算「11 月 18 日往后 30 天是哪天」，它一定会错，而用户会在第三天发现计划对不上日历。

---

## 为什么它不会变成又一份废掉的计划

五条硬约束，写进了代码而不是提示词：

1. **单日任务 ≤ 3 项**，单任务 ≤ 90 分钟 —— `plan new` 直接拦
2. **每个任务必须有可验收的 `verify`** —— 没有验收标准 = 无法判断做完没有
3. **每周至少 1 个缓冲日** —— 吸收欠账，避免断签引发雪崩
4. **完成率低于 50% 时禁止加码** —— 系统会明确提示「该降强度了」
5. **历史不可覆写** —— 每次调整生成新版本快照，随时能回看「当初为什么改」

---

## 数据存在哪

```
.mentor/
├── profile.json                 你的档案：经历、目标、约束、人格偏好
├── plans/<plan-id>.json         当前计划
├── plans/archive/<id>.vN.json   每次变更前的快照，只增不改
├── logs/YYYY-MM.jsonl           打卡流水，append-only，单行损坏不影响历史
├── reviews/YYYY-Www.md          周复盘
└── exports/                     导出的 md / ics
```

全部是纯文本。可以 git 追踪、可以 diff、可以随时导出走人。

> `.gitignore` 默认排除了 `.mentor/`（里面有你的个人经历）。如果你想让它跟着仓库一起成长，删掉那一行即可 —— 公开前记得检查 `profile.json`。

---

## 安装为 Skill

**WorkBuddy / 支持 skill 的 Agent**

```bash
git clone https://github.com/<you>/life-mentor.git \
  ~/.workbuddy/skills/life-mentor
```

重启会话后，说「帮我规划」「我想坚持一件事但总是放弃」「复盘一下这周」就会触发。

**Claude Code**

```bash
git clone https://github.com/<you>/life-mentor.git .claude/skills/life-mentor
```

**其它平台**：核心是 `SKILL.md`（工作流与约束）+ `scripts/mentor.py`（确定性计算）。任何能读文件、能执行命令的 Agent 都能用。

---

## 看一眼真实的复盘产出

```markdown
# 复盘 · 2026-W47

## 事实（机器统计，不要改写）
- 计划完成度：50%（本周 7 个计划日，已结束 2 天，打卡 2 天）
- 全周期日均完成率：83%
- 连续打卡：1 天（历史最佳 7 天）
- 受阻天数：1；跳过：0；漏打卡：0

## 归因（待填写）
> 只写可验证的原因，不写「不够努力」这种无法反驳也没法改的话。
```

事实部分由脚本产出，AI 只负责填归因和调整。**这样复盘就不会变成自我感动的散文。**

---

## 目录结构

```
life-mentor/
├── SKILL.md                      入口：工作流 + 铁律 + 命令速查
├── references/
│   ├── persona.md                双模式人格（严格 / 温和）
│   ├── interview.md              三轮访谈脚本与追问技巧
│   ├── diagnosis.md              五维诊断框架
│   ├── planning.md               计划设计规范与五种坏计划
│   └── domains/                  备考 / 健身 / 求职 / 副业模板
├── scripts/
│   ├── mentor.py                 统一 CLI
│   └── lib/                      store / cal / stats / render / validate / ics
├── assets/plan-schema.md         plan.json 字段说明
└── examples/demo-user/           一个跑了 9 天的真实档案，可直接看数据结构
```

想看效果，直接读 `examples/demo-user/`，里面有完整的计划、打卡流水、复盘和归档的旧版本。

---

## 设计原则（它不做什么）

- **不做心理诊断。** 出现持续低落或自伤信号时，`references/persona.md` 明确要求停止计划话题、建议寻求专业帮助。
- **不承诺结果。** 它只保证过程可执行，不保证你一定考上 / 瘦下来 / 拿到 offer。
- **不上传数据。** 所有内容都在本地 `.mentor/` 里。
- **不追求让你爽。** 完成率低的时候它会说「计划强度超了」，而不是「你已经很棒了」。

---

## Roadmap

- [ ] `mentor.py import --from markdown` 支持从已有笔记导入
- [ ] 打卡热力图（单文件 HTML，本地打开）
- [ ] 多计划并行（主线 + 副线）
- [ ] 更多领域模板：写作 / 语言学习 / 康复训练

---

## License

MIT
