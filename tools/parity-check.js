#!/usr/bin/env node
/* 一致性校验：读 tools/parity-fixture.json（由 Python 端生成），
 * 用 JS 版算法重算，逐字段比对。
 *
 *   python tools/gen-parity-fixture.py > tools/parity-fixture.json
 *   node tools/parity-check.js
 */
global.window = global;
var fs = require('fs');
var path = require('path');

require('../app/js/core/cal.js');
require('../app/js/core/stats.js');
var LM = global.LM;

var fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'parity-fixture.json'), 'utf8'));
var failures = 0;
var checks = 0;

function eq(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) < 1e-6;
  return JSON.stringify(a) === JSON.stringify(b);
}

function check(label, got, want) {
  checks++;
  if (!eq(got, want)) {
    failures++;
    console.log('  \u2717 ' + label + ': got=' + JSON.stringify(got) + ' want=' + JSON.stringify(want));
  }
}

/* 周编号 */
Object.keys(fixture.week_keys).forEach(function (d) {
  check('weekKey ' + d, LM.cal.weekKey(LM.cal.parseDate(d)), fixture.week_keys[d]);
});

var ref = LM.cal.parseDate(fixture.ref);

fixture.cases.forEach(function (c) {
  var profile = { resilience: { grace_per_week: c.grace, max_carry_days: c.max_carry == null ? 2 : c.max_carry } };
  var s = LM.stats.compute(fixture.plan, c.logs, ref, profile);
  var w = LM.stats.weekStats(fixture.plan, c.logs, ref);
  var e = c.expect;
  var before = failures;
  var tag = '[' + c.name + '] ';

  check(tag + 'streak', s.streak, e.streak);
  check(tag + 'best_streak', s.best_streak, e.best_streak);
  check(tag + 'cumulative_days', s.cumulative_days, e.cumulative_days);
  check(tag + 'effective_days', s.effective_days, e.effective_days);
  check(tag + 'done_tasks', s.done_tasks, e.done_tasks);
  check(tag + 'day_rate', Math.round(s.day_rate * 1e6) / 1e6, e.day_rate);
  check(tag + 'percent', s.percent, e.percent);
  check(tag + 'carryover', s.carryover.length, e.carryover);
  check(tag + 'carryover_dates', Array.from(new Set(s.carryover.map(function (x) { return x.from_date; }))).sort(), e.carryover_dates);
  check(tag + 'blocked_dates', s.blocked_dates, e.blocked_dates);
  check(tag + 'skipped_dates', s.skipped_dates, e.skipped_dates);
  check(tag + 'missing_dates', s.missing_dates, e.missing_dates);
  check(tag + 'grace_weeks_used', s.grace_weeks_used, e.grace_weeks_used);
  check(tag + 'needs_adapt', s.needs_adapt, e.needs_adapt);
  check(tag + 'week_key', w.week, e.week_key);
  check(tag + 'week_planned_days', w.planned_days, e.week_planned_days);
  check(tag + 'week_score', Math.round(w.score * 1e6) / 1e6, e.week_score);

  if (failures === before) console.log('\u2713 ' + c.name);
});

console.log('\n' + (failures === 0
  ? 'ALL PASS (' + checks + ' 项比对)'
  : 'FAIL ' + failures + '/' + checks));
process.exit(failures === 0 ? 0 : 1);
