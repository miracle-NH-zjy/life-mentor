/* 统计层：与 scripts/lib/stats.py 逐函数对应，保证两端算出的数字一致。
 *
 * 宽容原则：
 * · 累计天数永不归零，一次中断不会让之前的努力作废
 * · 每周允许 grace_per_week 天缺勤不打断连击（自动生效，无需操作）
 * · 主动 skip 是计划的一部分，不算断签；blocked 如实上报，同样不打断
 * · 未完成的任务顺延 max_carry_days 天，过期才真正失效
 */
(function (global) {
  'use strict';
  var LM = global.LM || (global.LM = {});
  var cal = LM.cal;

  var SCORE = { done: 1.0, partial: 0.5, skip: 0.0, blocked: 0.0 };
  var RECORDED = ['done', 'partial', 'skip', 'blocked'];
  var DEFAULT_RESILIENCE = { grace_per_week: 1, max_carry_days: 2, count_skip_as_break: false };

  function resilience(profile) {
    var cfg = Object.assign({}, DEFAULT_RESILIENCE);
    if (profile && profile.resilience) Object.assign(cfg, profile.resilience);
    return cfg;
  }

  function dayStatus(log) { return (log && log.status) || 'missing'; }

  function isRestDay(entry) { return !!entry && !(entry.tasks && entry.tasks.length); }

  function compute(plan, latestLogs, ref, profile) {
    ref = ref || cal.today();
    latestLogs = latestLogs || {};
    var days = plan.days || [];
    var start = cal.parseDate(plan.start_date);
    var end = cal.parseDate(plan.end_date);
    var cfg = resilience(profile);
    var grace = Math.max(0, parseInt(cfg.grace_per_week, 10) || 0);
    var maxCarry = Math.max(0, parseInt(cfg.max_carry_days, 10) || 0);

    var horizon = end < ref ? end : ref;
    var elapsed = cal.dateRange(start, horizon);
    var remain = ref < end ? cal.dateRange(cal.addDays(ref, 1), end) : [];
    var settled = elapsed.filter(function (d) { return d < ref; });

    var byDate = {};
    days.forEach(function (d) { byDate[d.date] = d; });

    var totalTasks = 0;
    days.forEach(function (d) { totalTasks += (d.tasks || []).length; });
    var doneTasks = 0;
    days.forEach(function (d) {
      var log = latestLogs[d.date];
      if (log && log.done_tasks) doneTasks += log.done_tasks.length;
    });
    if (doneTasks > totalTasks) doneTasks = totalTasks;

    var blocked = [], skipped = [], missing = [], cumulative = 0, effective = 0;
    elapsed.forEach(function (d) {
      var key = cal.fmt(d);
      var st = dayStatus(latestLogs[key]);
      if (RECORDED.indexOf(st) >= 0) cumulative += 1;
      if (st === 'done' || st === 'partial') effective += 1;
      if (st === 'blocked') blocked.push(key);
      else if (st === 'skip') skipped.push(key);
      else if (st === 'missing' && d < ref) missing.push(key);
    });

    var scored = settled.map(function (d) { return SCORE[dayStatus(latestLogs[cal.fmt(d)])] || 0; });
    var dayRate = scored.length ? scored.reduce(function (a, b) { return a + b; }, 0) / scored.length : 0;

    var walk = walkStreak(elapsed.slice().reverse(), latestLogs, byDate, grace);
    var allUpToRef = cal.dateRange(start, horizon);
    var best = bestStreak(allUpToRef, latestLogs, byDate, grace);

    var byPhase = {};
    settled.forEach(function (d) {
      var ph = cal.phaseFor(d, plan.phases || []) || '未分组';
      var bucket = byPhase[ph] || (byPhase[ph] = { days: 0, score: 0 });
      bucket.days += 1;
      bucket.score += SCORE[dayStatus(latestLogs[cal.fmt(d)])] || 0;
    });

    var todayKey = cal.fmt(ref);
    var todayEntry = byDate[todayKey] || null;
    var pendingToday = [];
    if (todayEntry) {
      var doneIds = ((latestLogs[todayKey] || {}).done_tasks) || [];
      pendingToday = (todayEntry.tasks || []).filter(function (t) { return doneIds.indexOf(t.id) < 0; });
    }

    return {
      plan_id: plan.id,
      version: plan.version || 1,
      goal: plan.goal || '',
      domain: plan.domain || '',
      start_date: plan.start_date,
      end_date: plan.end_date,
      total_days: days.length,
      elapsed_days: elapsed.length,
      remaining_days: remain.length,
      total_tasks: totalTasks,
      done_tasks: doneTasks,
      task_rate: totalTasks ? doneTasks / totalTasks : 0,
      day_rate: dayRate,
      percent: days.length ? Math.round(1000 * elapsed.length / days.length) / 10 : 0,
      streak: walk.streak,
      best_streak: best,
      cumulative_days: cumulative,
      effective_days: effective,
      grace_weeks_used: Object.keys(walk.used).sort(),
      grace_per_week: grace,
      carryover: carryover(plan, latestLogs, ref, maxCarry),
      blocked_dates: blocked,
      skipped_dates: skipped,
      missing_dates: missing,
      by_phase: byPhase,
      today: todayKey,
      today_entry: todayEntry,
      today_pending_tasks: pendingToday,
      today_log: latestLogs[todayKey] || null,
      week: cal.weekKey(ref),
      needs_adapt: elapsed.length >= 7 && dayRate < 0.5,
      in_range: start <= ref && ref <= end
    };
  }

  function walkStreak(order, latestLogs, byDate, grace) {
    var streak = 0, used = {};
    for (var i = 0; i < order.length; i++) {
      var d = order[i], key = cal.fmt(d);
      var st = dayStatus(latestLogs[key]);
      if (RECORDED.indexOf(st) >= 0) { streak += 1; continue; }
      if (isRestDay(byDate[key])) continue;
      var wk = cal.weekKey(d);
      if ((used[wk] || 0) < grace) { used[wk] = (used[wk] || 0) + 1; continue; }
      break;
    }
    return { streak: streak, used: used };
  }

  function bestStreak(order, latestLogs, byDate, grace) {
    var best = 0, run = 0, used = {};
    order.forEach(function (d) {
      var key = cal.fmt(d);
      var st = dayStatus(latestLogs[key]);
      if (RECORDED.indexOf(st) >= 0) { run += 1; return; }
      if (isRestDay(byDate[key])) return;
      var wk = cal.weekKey(d);
      if ((used[wk] || 0) < grace) { used[wk] = (used[wk] || 0) + 1; return; }
      if (run > best) best = run;
      run = 0;
    });
    return Math.max(best, run);
  }

  /* 过去 maxDays 天内没做完、且没被主动跳过的任务。过期即失效。 */
  function carryover(plan, latestLogs, ref, maxDays) {
    if (maxDays <= 0) return [];
    var byDate = {};
    (plan.days || []).forEach(function (d) { byDate[d.date] = d; });
    var out = [];
    for (var offset = 1; offset <= maxDays; offset++) {
      var d = cal.addDays(ref, -offset), key = cal.fmt(d);
      var entry = byDate[key];
      if (!entry) continue;
      var log = latestLogs[key] || {};
      if (log.status === 'skip') continue;
      var doneIds = log.done_tasks || [];
      (entry.tasks || []).forEach(function (t) {
        if (doneIds.indexOf(t.id) >= 0) return;
        out.push({
          task: t,
          from_date: key,
          age_days: offset,
          expires_in: maxDays - offset
        });
      });
    }
    return out;
  }

  function weekSlice(plan, latestLogs, ref) {
    var b = cal.weekBounds(ref);
    var out = [];
    cal.dateRange(b.start, b.end).forEach(function (d) {
      var key = cal.fmt(d);
      var entry = null;
      (plan.days || []).forEach(function (x) { if (x.date === key) entry = x; });
      out.push({ date: key, plan: entry, log: latestLogs[key] || null });
    });
    return out;
  }

  function weekStats(plan, latestLogs, ref) {
    var rows = weekSlice(plan, latestLogs, ref);
    var planned = rows.filter(function (r) { return r.plan; });
    /* 分母只算已经过完的日子，未来几天不该拉低本周成绩 */
    var t = cal.today();
    var settled = planned.filter(function (r) { return cal.parseDate(r.date) < t; });
    var scored = settled.map(function (r) { return SCORE[dayStatus(r.log)] || 0; });
    return {
      week: cal.weekKey(ref),
      planned_days: planned.length,
      settled_days: settled.length,
      logged_days: rows.filter(function (r) { return r.log; }).length,
      score: scored.length ? Math.round(1000 * scored.reduce(function (a, b) { return a + b; }, 0) / scored.length) / 1000 : 0,
      rows: rows
    };
  }

  LM.stats = {
    SCORE: SCORE,
    RECORDED: RECORDED,
    DEFAULT_RESILIENCE: DEFAULT_RESILIENCE,
    compute: compute,
    carryover: carryover,
    weekSlice: weekSlice,
    weekStats: weekStats,
    resilience: resilience
  };
})(window);
