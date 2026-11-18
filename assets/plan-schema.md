# plan.json 字段说明

`plan scaffold` 生成的骨架已经带好日期和空任务位，你只需要填 `phases` 和每天的 `tasks`。
导入前先用 `plan new --file` 校验，它会把下面标 **硬约束** 的规则逐条检查。

---

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 计划唯一标识，建议 `plan-YYYY-MM` |
| `version` | int | 自动 | 由脚本维护，不要手改 |
| `goal` | string | ✅ | 一句话目标，可判定成败 |
| `domain` | string | | `exam-prep` / `fitness` / `job-hunt` / `side-hustle` / 自定义 |
| `start_date` | `YYYY-MM-DD` | ✅ | 起始日 |
| `end_date` | `YYYY-MM-DD` | ✅ | 结束日，必须与 `days` 覆盖范围一致 |
| `buffer_weekday` | int | | 每周缓冲日，0=周一 … 6=周日，默认 6 |
| `status` | string | | `active` / `archived` / `done` |
| `phases` | array | | 阶段划分 |
| `days` | array | ✅ | 逐日安排，**必须日期连续、升序、无缺漏** |
| `history` | array | 自动 | 版本变更记录，由脚本追加 |

---

## phases[]

| 字段 | 说明 |
|---|---|
| `name` | 阶段名，如「P1 打通工具链」 |
| `start` / `end` | 阶段起止日期 |
| `focus` | 这一阶段的重心，一句话 |

每个阶段应当有一个**可交付物**，而不只是时间跨度。详见 `references/planning.md`。

---

## days[]

| 字段 | 必填 | 说明 |
|---|---|---|
| `date` | ✅ | `YYYY-MM-DD`，必须从 `start_date` 连续到 `end_date` |
| `weekday` | 自动 | 脚本会补 |
| `phase` | 自动 | 留空则由 `phases` 推导 |
| `is_buffer` | 自动 | 缓冲日不排任务，只补欠账 |
| `tasks` | ✅ | 任务数组，**单日硬上限 3 项** |
| `note` | | 当天备注 |

---

## tasks[]

| 字段 | 必填 | 规则 |
|---|---|---|
| `id` | ✅ | 计划内唯一。用脚本给的默认值 `dNNtM` |
| `title` | ✅ | 动词开头，能直接动手。禁止「学习/了解/熟悉/掌握」开头 |
| `est_min` | ✅ | 30–90 分钟。**超过 90 必须拆** |
| `verify` | ✅ | 能被第三方检查的证据，不是自我感觉 |

`verify` 写不好的话，这个任务等于没有验收标准。判断方法：**如果验收不通过，你能不能明确指出是哪一条没过？**

---

## 最小可运行示例

```json
{
  "id": "plan-2026-11",
  "goal": "两周内能从零跑通 STM32 点灯与串口",
  "domain": "exam-prep",
  "start_date": "2026-11-18",
  "end_date": "2026-11-19",
  "buffer_weekday": 6,
  "status": "active",
  "phases": [
    { "name": "P1 打通工具链", "start": "2026-11-18", "end": "2026-11-19",
      "focus": "第一次让板子按我的指令动作" }
  ],
  "days": [
    {
      "date": "2026-11-18", "weekday": "周三", "phase": "P1 打通工具链",
      "is_buffer": false,
      "tasks": [
        { "id": "d01t1", "title": "装好 Keil 并跑通空白工程", "est_min": 60,
          "verify": "能编译下载，复位后不报错" }
      ]
    },
    {
      "date": "2026-11-19", "weekday": "周四", "phase": "P1 打通工具链",
      "is_buffer": false,
      "tasks": [
        { "id": "d02t1", "title": "点亮 PC13 LED 并改成 1Hz 闪烁", "est_min": 45,
          "verify": "10 秒内数到 5 次闪烁" }
      ]
    }
  ]
}
```

---

## 校验会拦下什么

| 规则 | 级别 |
|---|---|
| 日期不连续 / 顺序错乱 / 超出周期 | 错误 |
| 单日任务 > 3 项 | 错误 |
| 单任务 > 90 分钟 | 错误 |
| 任务缺 `title` / `est_min` / `verify` | 错误 |
| 任务 id 重复 | 错误 |
| 单日总时长超过档案里的可用时间 | 警告 |
| 7 天排满无缓冲日 | 警告 |
| 缓冲日安排了任务 | 警告 |

错误必须改，警告建议改。`--force` 能跳过错误，但跳过之后计划大概率执行不了。
