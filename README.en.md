# life-mentor

> Turns "I want to be better" into a checklist you can actually tick off each day.

[中文文档 →](README.md)

A skill for AI agents. You describe your background and what you want. It runs a structured interview, diagnoses your real constraints, and generates a day-by-day plan where **every task has a verifiable completion criterion**. Then it handles daily check-ins, weekly reviews, and plan adjustments based on what actually happened.

Not a to-do app. Not a motivational generator. More like a coach who will tell you "this goal is not realistic" instead of writing you a prettier plan.

```
$ mentor status

Goal:   Get every module of the embedded competition working end-to-end in 30 days
Period: 2026-11-09 → 2026-12-08 (plan v2, 30 days)
Progress: [███████░░░░░░░░░░░░░] 33.3%  Day 10 of 30

2026-11-18 Wed · Day 10/30 · P2 Peripherals
───────────────────────────────────────────
 · 1. External interrupt + rotary encoder direction    75min
     verify: forward/reverse counts match, no missed steps at speed
```

---

## Why this exists

Most goal-tracking fails for three reasons, none of which is laziness:

1. **A wish is not a plan.** "Learn English" and "memorise 30 words and write one sentence each, tonight at 20:00" are separated by a whole decomposition process nobody teaches.
2. **Plans exceed real capacity.** You schedule 6 hours based on your ideal self, you actually have 1, day three collapses, you quit.
3. **One miss resets everything.** No buffer, so a missed day equals failure, failure equals restart, restart equals zero.

life-mentor is built around three answers: **interview before planning**, **every task must be verifiable**, and **when completion drops, lower the intensity — never raise it**.

---

## Quick start

Python 3.9+. Zero third-party dependencies.

```bash
git clone https://github.com/<you>/life-mentor.git
cd life-mentor

python scripts/mentor.py init --dir . --name Sam --goal "Ship a working prototype in 30 days"
python scripts/mentor.py plan scaffold --start 2026-11-18 --days 30 -o plan.json
# fill in phases + tasks, then:
python scripts/mentor.py plan new --file plan.json
python scripts/mentor.py checkin --status done
python scripts/mentor.py status
python scripts/mentor.py review
```

---

## Commands

| Purpose | Command |
|---|---|
| Init profile | `mentor.py init --dir . --name Sam --goal "..."` |
| View/edit profile | `mentor.py profile show` / `profile set --set constraints.time_per_day_min=90` |
| Generate day-by-day skeleton | `mentor.py plan scaffold --start 2026-11-18 --days 30 -o plan.json` |
| Import + validate | `mentor.py plan new --file plan.json` |
| View today / week / all | `mentor.py plan show` / `--week` / `--all` |
| Check in | `mentor.py checkin --status done\|partial\|skip\|blocked` |
| Progress | `mentor.py status` (`--json` for machines) |
| Weekly review | `mentor.py review` |
| Adjust plan | `mentor.py plan amend --file patch.json --reason "..."` |
| Export | `mentor.py export --format md\|ics --pending` |
| Consistency check | `mentor.py doctor` |

---

## Division of labour

**The model diagnoses, judges, and writes content. The script owns every date calculation and every bit of state.**

Ask a language model "what date is 30 days after 18 November" and it will eventually be wrong — and the user finds out on day three, when the plan no longer lines up with the calendar.

---

## Hard constraints (enforced in code, not in a prompt)

- Max **3 tasks per day**, max **90 minutes per task**
- Every task needs a `verify` field that a third party could check
- At least **one buffer day per week**
- When completion rate drops below 50%, the system tells you to **cut intensity**
- Plan history is **never overwritten** — every amendment creates a versioned snapshot

---

## Where data lives

```
.mentor/
├── profile.json                 background, goals, constraints, tone preference
├── plans/<plan-id>.json         current plan
├── plans/archive/<id>.vN.json   snapshot before every change, append-only
├── logs/YYYY-MM.jsonl           check-in stream, append-only
├── reviews/YYYY-Www.md          weekly reviews
└── exports/
```

Plain text. Git-trackable, diffable, and yours to take elsewhere.

---

## Install as a skill

**WorkBuddy / skill-aware agents**

```bash
git clone https://github.com/<you>/life-mentor.git ~/.workbuddy/skills/life-mentor
```

**Claude Code**

```bash
git clone https://github.com/<you>/life-mentor.git .claude/skills/life-mentor
```

The core is `SKILL.md` (workflow + guardrails) plus `scripts/mentor.py` (deterministic computation). Any agent that can read files and run commands can use it.

---

## What it refuses to do

- **No psychological diagnosis.** On signs of persistent low mood or self-harm, the skill stops the planning conversation and points to professional help.
- **No promises about outcomes.** It guarantees an executable process, not a result.
- **No data upload.** Everything stays in your local `.mentor/` directory.
- **No flattery.** When your completion rate is low it says "the plan is too heavy", not "you're doing great".

---

## Structure

```
life-mentor/
├── SKILL.md                      entry point: workflow, guardrails, command reference
├── references/
│   ├── persona.md                dual-mode persona (strict / gentle)
│   ├── interview.md              3-round interview script
│   ├── diagnosis.md              5-dimension diagnostic framework
│   ├── planning.md               planning rules + 5 anti-patterns
│   └── domains/                  exam prep / fitness / job hunt / side projects
├── scripts/
│   ├── mentor.py                 CLI
│   └── lib/                      store / cal / stats / render / validate / ics
├── assets/plan-schema.md         plan.json field reference
└── examples/demo-user/           a real profile with 9 days of history
```

---

## License

MIT
