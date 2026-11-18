/* 应用层：视图渲染 + 交互。
 *
 * 设计取舍：
 * · 不引入任何框架与构建步骤，GitHub Pages 直接托管，双击 index.html 也能跑
 * · 勾选任务先落草稿，点「提交打卡」才写入流水，避免误触污染统计
 * · 支持补录：从复盘页点过去的缺卡日，会在今日页以「补录」模式打开
 */
(function () {
  'use strict';

  var LM = window.LM;
  var cal = LM.cal, store = LM.store, stats = LM.stats, mot = LM.motivation;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var VIEW = 'today';
  var ui = {
    date: cal.fmt(cal.today()),   // 当前操作日期（补录时会指向过去）
    quote: '',
    flash: ''
  };

  /* ------------------------------------------------------------ 小工具 */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pct(x) { return Math.round((x || 0) * 100); }
  function clampPct(x) { return Math.max(0, Math.min(100, x)); }

  var toastTimer = null;
  function toast(msg) {
    var el = $('#toast');
    el.textContent = msg;
    el.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('is-on'); }, 2600);
  }

  function entryFor(dateKey) {
    var plan = store.plan();
    if (!plan) return null;
    for (var i = 0; i < (plan.days || []).length; i++) {
      if (plan.days[i].date === dateKey) return plan.days[i];
    }
    return null;
  }

  /* 草稿：勾选状态、备注、精力，先存本地，提交打卡时清空 */
  function getDraft(dateKey) {
    var st = store.state();
    var d = (st.drafts || {})[dateKey];
    if (!d) d = { tasks: [], note: '', energy: 3, status: null, evidence: [] };
    if (!d.evidence) d.evidence = [];
    return d;
  }
  function saveDraft(dateKey, patch) {
    var st = store.state();
    st.drafts = st.drafts || {};
    var cur = st.drafts[dateKey] || { tasks: [], note: '', energy: 3, status: null, evidence: [] };
    Object.assign(cur, patch || {});
    st.drafts[dateKey] = cur;
    store.saveState(st);
    return cur;
  }
  function clearDraft(dateKey) {
    var st = store.state();
    if (st.drafts) delete st.drafts[dateKey];
    store.saveState(st);
  }

  /* ------------------------------------------------------------ 今日视图 */
  function renderToday() {
    var plan = store.plan();
    var root = $('#view-today');
    if (!plan) return;

    var profile = store.profile();
    var logs = store.latestByDate();
    var s = stats.compute(plan, logs, cal.parseDate(ui.date), profile);
    var d = cal.parseDate(ui.date);
    var isToday = ui.date === cal.fmt(cal.today());
    var entry = s.today_entry;
    var log = s.today_log;
    var draft = getDraft(ui.date);
    /* 编辑模式下勾选以草稿为准，否则以已保存的记录为准 */
    var doneIds = (log && !draft.editing) ? (log.done_tasks || []) : (draft.tasks || []);

    var html = '';

    /* 补录提示 */
    if (!isToday) {
      html += '<div class="card card-flat" style="display:flex;align-items:center;justify-content:space-between;gap:12px">' +
        '<div><div class="row-title">正在补录 ' + d.getMonth() + 1 + ' 月 ' + d.getDate() + ' 日</div>' +
        '<div class="row-sub">补录会写入当天的打卡流水，历史依然留痕</div></div>' +
        '<button class="link-btn" data-act="back-today">回到今天</button></div>';
    }

    /* 主卡 */
    var phase = entry ? entry.phase : '';
    html += '<div class="hero">' +
      '<div class="hero-top">' +
        '<div>' +
          '<div class="hero-date">' + d.getFullYear() + ' 年 ' + (d.getMonth() + 1) + ' 月 ' + d.getDate() + ' 日 · ' + cal.weekdayCn(d) + '</div>' +
          '<div class="hero-day">第 ' + (s.in_range ? cal.dayIndex(d, cal.parseDate(plan.start_date)) : '—') +
            '<small>/ ' + plan.days.length + '</small></div>' +
          (phase ? '<div class="hero-phase">' + esc(phase) + '</div>' : '') +
        '</div>' +
        '<div class="ring" style="--p:' + clampPct(s.percent) + '">' +
          '<div class="ring-val">' + Math.round(s.percent) + '<span>%</span></div>' +
        '</div>' +
      '</div>' +
      '<div class="hero-meta">' +
        '<div class="meta-item"><b>' + s.streak + '</b><span>连续打卡</span></div>' +
        '<div class="meta-item"><b>' + s.cumulative_days + '</b><span>累计天数</span></div>' +
        '<div class="meta-item"><b>' + pct(s.day_rate) + '%</b><span>完成率</span></div>' +
      '</div>' +
    '</div>';

    if (!s.in_range) {
      html += '<div class="card"><div class="row-title">这一天不在计划周期内</div>' +
        '<div class="row-sub">计划覆盖 ' + plan.start_date + ' → ' + plan.end_date + '</div></div>';
      root.innerHTML = html;
      return;
    }

    /* 打卡后的语录 */
    if (ui.quote) {
      html += '<div class="quote">' + esc(ui.quote) + '</div>';
    }

    /* 任务 */
    var tasks = (entry && entry.tasks) || [];
    if (tasks.length) {
      var doneCount = tasks.filter(function (t) { return doneIds.indexOf(t.id) >= 0; }).length;
      html += '<div class="card">' +
        '<div class="card-head"><div class="card-title">' + (isToday ? '今日任务' : '当天任务') + '</div>' +
        '<div class="card-note">' + doneCount + '/' + tasks.length + ' 已完成</div></div>';
      tasks.forEach(function (t) {
        var isDone = doneIds.indexOf(t.id) >= 0;
        html += '<div class="task' + (isDone ? ' is-done' : '') + '" data-act="toggle-task" data-id="' + esc(t.id) + '">' +
          '<div class="check"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="var(--brand-ink)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 12.5l5 5L19.5 7"></path></svg></div>' +
          '<div class="task-body">' +
            '<div class="task-title">' + esc(t.title) + '</div>' +
            '<div class="task-sub"><span>' + (t.est_min || 0) + ' 分钟</span>' +
              (entry.is_buffer ? '<span class="tag">缓冲日</span>' : '') +
            '</div>' +
            (t.verify ? '<div class="task-verify"><b>验收 </b>' + esc(t.verify) + '</div>' : '') +
          '</div>' +
        '</div>';
      });
      html += '</div>';
    } else {
      html += '<div class="card card-flat"><div class="row-title">今天是缓冲日</div>' +
        '<div class="row-sub">没有安排任务。休息是计划的一部分，不用有负担。</div></div>';
    }

    /* 打卡面板 */
    if (log && !draft.editing) {
      html += renderLogResult(log, entry);
    } else {
      html += renderCheckinPanel(draft, doneIds, tasks);
    }

    /* 待补任务 */
    var carry = s.carryover.filter(function (c) { return c.from_date !== ui.date; });
    if (carry.length) {
      html += '<div class="card card-flat section-gap">' +
        '<div class="card-head"><div class="card-title">从前面顺延过来</div>' +
        '<div class="card-note">最多留 ' + stats.resilience(store.profile()).max_carry_days + ' 天</div></div>';
      carry.forEach(function (c) {
        html += '<div class="carry-item"><div class="carry-bar"></div><div class="carry-body">' +
          '<div class="carry-title">' + esc(c.task.title) + '</div>' +
          '<div class="carry-meta"><span>' + c.from_date.slice(5) + ' 未完成</span>' +
          '<span>' + (c.expires_in > 0 ? '还有 ' + c.expires_in + ' 天失效' : '今天最后一天') + '</span></div>' +
        '</div></div>';
      });
      html += '</div>';
    }

    root.innerHTML = html;
  }

  function renderLogResult(log, entry) {
    var labels = { done: '完成', partial: '部分完成', skip: '主动跳过', blocked: '受阻' };
    var cls = { done: 'tag-ok', partial: 'tag-warn', skip: '', blocked: 'tag-danger' };
    var total = entry && entry.tasks ? entry.tasks.length : 0;
    var doneN = (log.done_tasks || []).length;
    var h = '<div class="card">' +
      '<div class="card-head"><div class="card-title">已打卡</div>' +
      '<span class="tag ' + (cls[log.status] || '') + '">' + (labels[log.status] || log.status) + '</span></div>' +
      '<div class="row"><div class="row-main"><div class="row-title">' +
        (log.status === 'done' ? '今天的任务全部完成' :
         log.status === 'partial' ? '完成了 ' + doneN + ' / ' + total + ' 项' :
         log.status === 'skip' ? '今天主动休息，没有硬撑' : '今天被挡住了') +
      '</div><div class="row-sub mono">' + (log.at || '').replace('T', ' ').slice(5, 16) +
        (log.energy ? ' · 精力 ' + log.energy + '/5' : '') + '</div></div></div>';
    if (log.note) {
      h += '<div class="hint-box">' + esc(log.note) + '</div>';
    }
    if ((log.evidence || []).length) {
      h += '<div class="evidence-row">';
      log.evidence.forEach(function (ev) {
        if (ev.thumb) {
          h += '<img class="evidence-thumb" src="' + ev.thumb + '" alt="' + esc(ev.name) + '">';
        } else {
          h += '<span class="evidence-file">📎 <span>' + esc(ev.name || ev) + '</span></span>';
        }
      });
      h += '</div>';
    }
    h += '<div style="margin-top:14px"><button class="ghost-line" data-act="edit-log">修改这条打卡记录</button></div>';
    h += '</div>';
    return h;
  }

  function renderCheckinPanel(draft, doneIds, tasks) {
    var total = tasks.length;
    var doneN = tasks.filter(function (t) { return doneIds.indexOf(t.id) >= 0; }).length;
    var auto = total === 0 ? 'skip' : (doneN === total ? 'done' : (doneN > 0 ? 'partial' : 'blocked'));
    var cur = draft.status || auto;

    var opts = [
      { s: 'done', lbl: '全部完成', hint: doneN + '/' + total + ' 项' },
      { s: 'partial', lbl: '部分完成', hint: doneN + '/' + total + ' 项' },
      { s: 'skip', lbl: '主动跳过', hint: '不算断签' },
      { s: 'blocked', lbl: '遇到阻碍', hint: '如实记下原因' }
    ];

    var h = '<div class="card section-gap">' +
      '<div class="card-head"><div class="card-title">打卡</div>' +
      '<div class="card-note">勾选任务后再提交</div></div>' +
      '<div class="status-grid">';
    opts.forEach(function (o) {
      h += '<button class="status-btn' + (cur === o.s ? ' is-on' : '') + '" data-act="set-status" data-s="' + o.s + '">' +
        '<span class="dot"></span><span><span class="lbl">' + o.lbl + '</span>' +
        '<span class="hint">' + o.hint + '</span></span></button>';
    });
    h += '</div>';

    h += '<div class="field"><label class="field-label">' +
      (cur === 'blocked' ? '卡在哪（这条最重要，下次调计划靠它）' : '今天记一笔（可选）') + '</label>' +
      '<textarea id="noteInput" rows="3" placeholder="' +
        (cur === 'blocked' ? '例：实验课调课，整块时间被切碎，只看了半小时' : '例：Keil 装了三遍才对，串口驱动要单独装') +
      '">' + esc(draft.note || '') + '</textarea></div>';

    h += '<div class="field"><label class="field-label">精力</label><div class="moods" data-act="mood-group">';
    for (var i = 1; i <= 5; i++) {
      h += '<button class="mood' + ((draft.energy || 3) === i ? ' is-on' : '') + '" data-act="set-energy" data-v="' + i + '">' + i + '</button>';
    }
    h += '</div></div>';

    h += '<div class="field"><label class="field-label">凭证（可选）</label>' +
      '<button class="ghost-line" data-act="pick-evidence">上传截图或文件</button>';
    if ((draft.evidence || []).length) {
      h += '<div class="evidence-row">';
      draft.evidence.forEach(function (ev, idx) {
        if (ev.thumb) {
          h += '<img class="evidence-thumb" src="' + ev.thumb + '" alt="' + esc(ev.name) + '" data-act="rm-evidence" data-i="' + idx + '">';
        } else {
          h += '<span class="evidence-file" data-act="rm-evidence" data-i="' + idx + '">📎 <span>' + esc(ev.name) + '</span> ✕</span>';
        }
      });
      h += '</div>';
    }
    h += '</div>';

    h += '<button class="primary-btn" data-act="submit-checkin" data-s="' + cur + '">提交打卡</button>';
    h += '</div>';
    return h;
  }

  /* ------------------------------------------------------------ 计划视图 */
  function renderPlan() {
    var plan = store.plan();
    var root = $('#view-plan');
    if (!plan) { root.innerHTML = renderEmpty(); return; }

    var profile = store.profile();
    var logs = store.latestByDate();
    var s = stats.compute(plan, logs, cal.today(), profile);

    var h = '<div class="card">' +
      '<div class="card-title" style="margin-bottom:8px">目标</div>' +
      '<div style="font-size:17px;font-weight:600;line-height:1.5">' + esc(plan.goal || '（未填写）') + '</div>' +
      '<div class="row-sub" style="margin-top:8px">' + plan.start_date + ' → ' + plan.end_date +
        ' · 共 ' + plan.days.length + ' 天 · v' + (plan.version || 1) + '</div>' +
    '</div>';

    /* 总进度 */
    h += '<div class="card"><div class="card-head"><div class="card-title">进度</div>' +
      '<div class="card-note">已过 ' + s.elapsed_days + ' / ' + plan.days.length + ' 天</div></div><div class="bars">' +
      bar('时间进度', s.percent, 100, '') +
      bar('每日完成率', pct(s.day_rate), 100, s.day_rate < 0.5 ? 'is-danger' : (s.day_rate < 0.8 ? 'is-warn' : 'is-ok')) +
      bar('任务完成', pct(s.task_rate), 100, '') +
      '</div></div>';

    /* 阶段 */
    var phaseKeys = Object.keys(s.by_phase);
    if (phaseKeys.length && phaseKeys[0] !== '未分组') {
      h += '<div class="card"><div class="card-head"><div class="card-title">分阶段</div></div><div class="bars">';
      phaseKeys.forEach(function (k) {
        var b = s.by_phase[k];
        var rate = b.days ? b.score / b.days : 0;
        h += bar(k, pct(rate), 100, rate < 0.5 ? 'is-danger' : (rate < 0.8 ? 'is-warn' : 'is-ok'));
      });
      h += '</div></div>';
    }

    /* 热力图 */
    h += '<div class="card"><div class="card-head"><div class="card-title">全程</div>' +
      '<div class="card-note">点格子可以补录</div></div>';
    h += '<div class="heat">';
    var first = cal.parseDate(plan.start_date);
    for (var pad = 0; pad < cal.pyWeekday(first); pad++) h += '<div class="heat-cell" style="visibility:hidden"></div>';
    cal.dateRange(plan.start_date, plan.end_date).forEach(function (dt) {
      var key = cal.fmt(dt);
      var lg = logs[key];
      var cls = 'heat-cell';
      if (lg && lg.status) cls += ' is-' + lg.status;
      else if (cal.isBufferDay(dt, plan)) cls += ' is-buffer';
      if (key === cal.fmt(cal.today())) cls += ' is-today';
      h += '<div class="' + cls + '" data-act="jump-date" data-d="' + key + '">' + dt.getDate() + '</div>';
    });
    h += '</div>' + legend() + '</div>';

    /* 逐周明细 */
    var byWeek = {};
    (plan.days || []).forEach(function (day) {
      var wk = cal.weekKey(cal.parseDate(day.date));
      (byWeek[wk] || (byWeek[wk] = [])).push(day);
    });
    Object.keys(byWeek).sort().forEach(function (wk) {
      h += '<div class="card"><div class="card-head"><div class="card-title">' + wk + '</div>' +
        '<div class="card-note">' + byWeek[wk].length + ' 天</div></div>';
      byWeek[wk].forEach(function (day) {
        var lg = logs[day.date];
        var st = lg ? lg.status : 'missing';
        var dotColor = { done: 'var(--ok)', partial: 'var(--warn)', blocked: 'var(--danger)', skip: 'var(--text-3)' }[st] || 'var(--surface-3)';
        var n = (day.tasks || []).length;
        var firstTitle = n ? day.tasks[0].title : (cal.isBufferDay(cal.parseDate(day.date), plan) ? '缓冲日' : '无任务');
        h += '<div class="row" data-act="jump-date" data-d="' + day.date + '" style="cursor:pointer">' +
          '<span style="width:8px;height:8px;border-radius:50%;background:' + dotColor + ';flex:none"></span>' +
          '<div class="row-main"><div class="row-title" style="font-size:14px">' + esc(firstTitle) + '</div>' +
          '<div class="row-sub">' + (n > 1 ? '共 ' + n + ' 项' : (n ? '1 项' : '休息')) +
          (lg && lg.status === 'blocked' && lg.note ? ' · ' + esc(lg.note.slice(0, 18)) : '') + '</div></div>' +
          '<div class="row-date">' + day.date.slice(5) + '</div>' +
        '</div>';
      });
      h += '</div>';
    });

    root.innerHTML = h;
  }

  function bar(label, val, max, cls) {
    var w = clampPct(max ? (val / max) * 100 : 0);
    return '<div class="bar-row"><div class="bar-top"><span>' + esc(label) + '</span><b>' + val + '%</b></div>' +
      '<div class="bar-track"><div class="bar-fill ' + (cls || '') + '" style="width:' + w + '%"></div></div></div>';
  }

  function legend() {
    return '<div class="heat-legend">' +
      '<span><i style="background:var(--ok)"></i>完成</span>' +
      '<span><i style="background:var(--warn)"></i>部分</span>' +
      '<span><i style="background:var(--danger)"></i>受阻</span>' +
      '<span><i style="background:var(--muted-soft)"></i>跳过</span>' +
      '<span><i style="background:var(--surface-3)"></i>未打卡</span>' +
    '</div>';
  }

  /* ------------------------------------------------------------ 复盘视图 */
  function renderReview() {
    var plan = store.plan();
    var root = $('#view-review');
    if (!plan) { root.innerHTML = renderEmpty(); return; }

    var profile = store.profile();
    var logs = store.latestByDate();
    var ref = cal.today();
    var s = stats.compute(plan, logs, ref, profile);
    var w = stats.weekStats(plan, logs, ref);

    var h = '<div class="card">' +
      '<div class="card-head"><div class="card-title">本周 · ' + w.week + '</div>' +
      '<div class="card-note">计划 ' + w.planned_days + ' 天 · 打卡 ' + w.logged_days + ' 天</div></div>' +
      '<div class="heat" style="grid-template-columns:repeat(7,1fr)">';
    var labels = ['一', '二', '三', '四', '五', '六', '日'];
    for (var i = 0; i < 7; i++) {
      var row = w.rows[i];
      var lg = row.log;
      var cls = 'heat-cell';
      if (lg && lg.status) cls += ' is-' + lg.status;
      if (row.date === cal.fmt(ref)) cls += ' is-today';
      h += '<div class="' + cls + '" style="font-size:9px">' + labels[i] + '<br>' + row.date.slice(8) + '</div>';
    }
    h += '</div>' + legend() + '</div>';

    h += '<div class="card"><div class="card-head"><div class="card-title">本周数据</div></div><div class="bars">' +
      bar('完成度', pct(w.score), 100, w.score < 0.5 ? 'is-danger' : (w.score < 0.8 ? 'is-warn' : 'is-ok')) +
      '</div>' +
      '<div class="hero-meta" style="border-top:1px solid var(--line);margin-top:16px;padding-top:14px">' +
        '<div class="meta-item"><b>' + w.settled_days + '</b><span>已结算天数</span></div>' +
        '<div class="meta-item"><b>' + s.streak + '</b><span>连续打卡</span></div>' +
        '<div class="meta-item"><b>' + s.best_streak + '</b><span>历史最佳</span></div>' +
      '</div></div>';

    /* 卡点 */
    var blockedRows = Object.keys(logs).map(function (k) { return logs[k]; })
      .filter(function (l) { return l.status === 'blocked'; })
      .sort(function (a, b) { return b.date.localeCompare(a.date); })
      .slice(0, 6);

    if (blockedRows.length) {
      h += '<div class="card"><div class="card-head"><div class="card-title">卡点</div>' +
        '<div class="card-note">共 ' + s.blocked_dates.length + ' 天受阻</div></div>';
      blockedRows.forEach(function (l) {
        h += '<div class="row"><div class="row-main"><div class="row-title" style="font-size:14px">' +
          esc(l.note || '（没有记录原因）') + '</div>' +
          '<div class="row-sub">受阻的日子要把原因写清楚，改计划才有依据</div></div>' +
          '<div class="row-date">' + l.date.slice(5) + '</div></div>';
      });
      h += '</div>';
    }

    /* 缺卡 */
    var missingRecent = s.missing_dates.slice(-6).reverse();
    if (missingRecent.length) {
      h += '<div class="card"><div class="card-head"><div class="card-title">缺卡</div>' +
        '<div class="card-note">这些天没有记录</div></div>';
      missingRecent.forEach(function (k) {
        h += '<div class="row"><div class="row-main"><div class="row-title" style="font-size:14px">' +
          esc(cal.weekdayCn(cal.parseDate(k))) + ' 没有打卡</div>' +
          '<div class="row-sub">想起来做了什么可以补录</div></div>' +
          '<button class="link-btn" data-act="jump-date" data-d="' + k + '">补录</button></div>';
      });
      h += '</div>';
    }

    if (s.needs_adapt) {
      h += '<div class="card" style="border-color:var(--danger)">' +
        '<div class="card-title" style="color:var(--danger);margin-bottom:8px">系统判断</div>' +
        '<div style="font-size:14px;line-height:1.6">日均完成率低于 50% 且已过 7 天以上。' +
        '这不是意志力问题，是计划强度与承载力不匹配。</div>' +
        '<div class="hint-box">下一步应该<b>下调任务量</b>，而不是加码。在设置里把「每天可用时间」改小，重新生成计划。</div></div>';
    }

    h += '<div class="card"><div class="card-head"><div class="card-title">导出</div></div>' +
      '<button class="primary-btn" data-act="export-week">生成本周复盘 Markdown</button>' +
      '<div class="hint-box">复盘写清楚三件事：哪几天做到了、断在哪、下一版计划改什么。' +
      '没有这三条，复盘就只是情绪记录。</div></div>';

    root.innerHTML = h;
  }

  /* ------------------------------------------------------------ 设置视图 */
  function renderSettings() {
    var root = $('#view-settings');
    var plan = store.plan();
    var profile = store.profile();
    var res = stats.resilience(profile);
    var mcfg = mot.config(profile);

    var h = '<div class="card">' +
      '<div class="card-head"><div class="card-title">档案</div></div>' +
      '<div class="row"><div class="row-main"><div class="row-title">' + esc(profile.name || '还没有名字') + '</div>' +
      '<div class="row-sub">' + esc(profile.identity || '未填写身份') + '</div></div></div>' +
      (profile.goal && profile.goal.statement ?
        '<div class="hint-box">' + esc(profile.goal.statement) + '</div>' : '') +
      '<div class="hint-box">电脑端跑 <b>mentor.py</b> 做访谈和计划生成，' +
      '这里负责每天打开、勾选、打卡。两边用同一份 JSON，可以互相导入。</div>' +
    '</div>';

    /* 数据 */
    h += '<div class="card"><div class="card-head"><div class="card-title">数据</div>' +
      '<div class="card-note">' + (plan ? '已载入计划' : '还没有计划') + '</div></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">导入计划</div>' +
        '<div class="setting-desc">选择 plan-YYYY-MM.json（电脑端 plan new 的产物）</div></div>' +
        '<button class="link-btn" data-act="import-plan">选择</button></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">导入打卡记录</div>' +
        '<div class="setting-desc">选择 logs/YYYY-MM.jsonl，与现有记录自动合并去重</div></div>' +
        '<button class="link-btn" data-act="import-logs">选择</button></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">从备份恢复</div>' +
        '<div class="setting-desc">换手机时用，恢复全部数据</div></div>' +
        '<button class="link-btn" data-act="import-bundle">选择</button></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">导出给电脑端</div>' +
        '<div class="setting-desc">生成 plan.json 与按月拆分的 .jsonl，放回 .mentor/ 即可被 Python 版读取</div></div>' +
        '<button class="link-btn" data-act="export-python">导出</button></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">导出完整备份</div>' +
        '<div class="setting-desc">单个 JSON 文件，含计划、流水与全部设置</div></div>' +
        '<button class="link-btn" data-act="export-bundle">导出</button></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">清空全部数据</div>' +
        '<div class="setting-desc">不可撤销，建议先导出备份</div></div>' +
        '<button class="link-btn" style="color:var(--danger)" data-act="reset">清空</button></div>' +
    '</div>';

    /* 宽容 */
    h += '<div class="card"><div class="card-head"><div class="card-title">断签规则</div></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">每周豁免</div>' +
        '<div class="setting-desc">一周内允许几天缺勤不打断连击</div></div>' +
        '<div class="seg" data-act="set-grace">' + segBtn([0, 1, 2, 3], res.grace_per_week) + '</div></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">任务顺延上限</div>' +
        '<div class="setting-desc">没做完的任务最多往后带几天，过期即失效</div></div>' +
        '<div class="seg" data-act="set-carry">' + segBtn([0, 1, 2, 3], res.max_carry_days) + '</div></div>' +
      '<div class="hint-box">累计天数永不归零。主动跳过和如实上报受阻，都不算断签。</div>' +
    '</div>';

    /* 文案 */
    h += '<div class="card"><div class="card-head"><div class="card-title">励志文案</div>' +
      '<div class="card-note">' + (mcfg.enabled ? '已开启' : '已关闭') + '</div></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">启用</div>' +
        '<div class="setting-desc">打卡、恢复、里程碑、低谷时各给一句</div></div>' +
        '<div class="seg" data-act="set-mot-enabled">' +
          '<button data-v="1" class="' + (mcfg.enabled ? 'is-on' : '') + '">开</button>' +
          '<button data-v="0" class="' + (!mcfg.enabled ? 'is-on' : '') + '">关</button>' +
        '</div></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">来源</div>' +
        '<div class="setting-desc">mix 内置加自写，custom 只用自己写的</div></div>' +
        '<div class="seg" data-act="set-mot-mode">' +
          ['mix', 'builtin', 'custom'].map(function (m) {
            var lbl = { mix: '混合', builtin: '内置', custom: '自写' }[m];
            return '<button data-v="' + m + '" class="' + (mcfg.mode === m ? 'is-on' : '') + '">' + lbl + '</button>';
          }).join('') +
        '</div></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">写一条自己的</div>' +
        '<div class="setting-desc">支持 {streak} {cumulative} {percent} 占位符</div></div>' +
        '<button class="link-btn" data-act="add-quote">添加</button></div>' +
      '<div class="setting"><div class="setting-main"><div class="setting-title">管理已写的</div>' +
        '<div class="setting-desc">' + countCustom(mcfg) + ' 条自定义文案</div></div>' +
        '<button class="link-btn" data-act="list-quotes">查看</button></div>' +
    '</div>';

    /* 关于 */
    h += '<div class="card card-flat"><div class="card-title" style="margin-bottom:10px">关于</div>' +
      '<div style="font-size:13px;color:var(--text-2);line-height:1.7">' +
      '人生导师模拟器的打卡端。数据全部存在这台设备的浏览器里，不上传任何服务器。' +
      '清除浏览器数据会一并清除，记得定期导出备份。</div>' +
      '<div class="row-sub" style="margin-top:12px">life-mentor · 与 Python 版共用数据格式</div>' +
    '</div>';

    root.innerHTML = h;
  }

  function segBtn(values, cur) {
    return values.map(function (v) {
      return '<button data-v="' + v + '" class="' + (Number(cur) === v ? 'is-on' : '') + '">' + v + '</button>';
    }).join('');
  }

  function countCustom(cfg) {
    var n = 0;
    Object.keys(cfg.custom || {}).forEach(function (k) { n += (cfg.custom[k] || []).length; });
    return n;
  }

  /* ------------------------------------------------------------ 空状态 */
  function renderEmpty() {
    return '<div class="empty">' +
      '<div class="empty-icon"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M4 12.6l5 5L20 6.8"></path></svg></div>' +
      '<h2>还没有计划</h2>' +
      '<p>电脑端用 <b>mentor.py</b> 做完访谈并生成计划后，<br>把 plan 文件导入进来，就能每天打卡了。</p>' +
      '<button class="primary-btn" data-act="import-plan">导入计划文件</button>' +
      '<button class="ghost-line" data-act="load-demo">先看看示例档案长什么样</button>' +
      '</div>';
  }

  /* ------------------------------------------------------------ 主渲染 */
  function render() {
    var plan = store.plan();

    $$('.view').forEach(function (v) { v.hidden = v.dataset.view !== VIEW; });
    $$('.tab').forEach(function (t) { t.classList.toggle('is-active', t.dataset.tab === VIEW); });

    var eyebrow = '人生导师';
    var title = '今天';

    if (!plan) {
      eyebrow = '人生导师';
      title = '开始';
      $('#view-today').innerHTML = renderEmpty();
      $('#view-plan').innerHTML = renderEmpty();
      $('#view-review').innerHTML = renderEmpty();
      renderSettings();
      $('#topEyebrow').textContent = eyebrow;
      $('#topTitle').textContent = title;
      return;
    }

    var d = cal.parseDate(ui.date);
    if (VIEW === 'today') {
      title = ui.date === cal.fmt(cal.today()) ? '今天' : (d.getMonth() + 1) + ' 月 ' + d.getDate() + ' 日';
      eyebrow = cal.weekdayCn(d) + ' · ' + cal.weekKey(d);
      renderToday();
    } else if (VIEW === 'plan') {
      title = '计划';
      eyebrow = plan.days.length + ' 天 · v' + (plan.version || 1);
      renderPlan();
    } else if (VIEW === 'review') {
      title = '复盘';
      eyebrow = cal.weekKey(cal.today());
      renderReview();
    } else {
      title = '设置';
      eyebrow = '数据与规则';
      renderSettings();
    }

    $('#topEyebrow').textContent = eyebrow;
    $('#topTitle').textContent = title;
  }

  /* ------------------------------------------------------------ 打卡动作 */
  function submitCheckin(status) {
    var plan = store.plan();
    if (!plan) return;
    var entry = entryFor(ui.date);
    if (!entry) { toast('这一天不在计划周期内'); return; }

    var draft = getDraft(ui.date);
    var tasks = entry.tasks || [];
    var doneIds = (draft.tasks || []).filter(function (id) {
      return tasks.some(function (t) { return t.id === id; });
    });

    if ((status === 'done' || status === 'partial') && !doneIds.length) {
      toast('先勾选完成的任务，或者改成「主动跳过」');
      return;
    }
    if (status === 'partial' && doneIds.length === tasks.length) {
      status = 'done';
    }

    var record = {
      date: ui.date,
      at: cal.nowIso(),
      status: status,
      done_tasks: status === 'done' || status === 'partial' ? doneIds : [],
      note: draft.note || '',
      energy: draft.energy || 3
    };
    if ((draft.evidence || []).length) {
      record.evidence = draft.evidence.map(function (ev) {
        return { name: ev.name, thumb: ev.thumb || '', size: ev.size || 0 };
      });
    }
    if (status === 'blocked' && !record.note.trim()) {
      toast('受阻的话，把原因写一句，下次改计划要靠它');
      return;
    }

    store.appendLog(record);
    clearDraft(ui.date);

    /* 选一句合适的文案 */
    var logs = store.latestByDate();
    var s = stats.compute(plan, logs, cal.parseDate(ui.date), store.profile());
    var st = store.state();
    var ctx = {
      streak: s.streak,
      cumulative: s.cumulative_days,
      percent: Math.round(s.percent),
      days: s.cumulative_days,
      rate: pct(s.day_rate),
      name: (store.profile().name || '')
    };
    var scene = status === 'skip' ? 'skip' : (status === 'blocked' ? 'blocked' : 'done');
    if ([7, 14, 21, 30, 60, 100].indexOf(s.cumulative_days) >= 0) scene = 'milestone';
    else if (status === 'done' && s.streak === 1 && s.cumulative_days > 1) scene = 'recovery';
    else if (status === 'done' && s.needs_adapt) scene = 'low';

    var q = mot.pick({ motivation: store.profile().motivation }, scene, ctx, st.recentQuotes);
    if (q) store.rememberQuote(q);
    ui.quote = q;
    ui.flash = '';

    render();
    toast('已打卡 · ' + ({ done: '完成', partial: '部分完成', skip: '跳过', blocked: '受阻' }[status]));
  }

  /* ------------------------------------------------------------ 图片压缩 */
  function shrinkImage(file, maxW) {
    return new Promise(function (resolve) {
      var reader = new FileReader();
      reader.onload = function () {
        var img = new Image();
        img.onload = function () {
          var scale = Math.min(1, maxW / img.width);
          var w = Math.round(img.width * scale), h = Math.round(img.height * scale);
          var c = document.createElement('canvas');
          c.width = w; c.height = h;
          c.getContext('2d').drawImage(img, 0, 0, w, h);
          try {
            resolve(c.toDataURL('image/jpeg', 0.7));
          } catch (e) { resolve(''); }
        };
        img.onerror = function () { resolve(''); };
        img.src = reader.result;
      };
      reader.onerror = function () { resolve(''); };
      reader.readAsDataURL(file);
    });
  }

  /* ------------------------------------------------------------ 事件 */
  function onMainClick(e) {
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var act = el.dataset.act;

    if (act === 'toggle-task') {
      var log = store.todayLog(ui.date);
      if (log && !getDraft(ui.date).editing) {
        toast('已打卡。要改的话点下面的「修改这条打卡记录」');
        return;
      }
      var id = el.dataset.id;
      var draft = getDraft(ui.date);
      var list = (draft.tasks || []).slice();
      var i = list.indexOf(id);
      if (i >= 0) list.splice(i, 1); else list.push(id);
      saveDraft(ui.date, { tasks: list, status: null });
      render();
      return;
    }

    if (act === 'set-status') {
      var dr = getDraft(ui.date);
      var next = dr.status === el.dataset.s ? null : el.dataset.s;
      saveDraft(ui.date, { status: next });
      render();
      return;
    }

    if (act === 'set-energy') {
      saveDraft(ui.date, { energy: Number(el.dataset.v) });
      render();
      return;
    }

    if (act === 'submit-checkin') { submitCheckin(el.dataset.s); return; }

    if (act === 'pick-evidence') { $('#fileEvidence').click(); return; }

    if (act === 'rm-evidence') {
      var idx = Number(el.dataset.i);
      var d2 = getDraft(ui.date);
      var evs = (d2.evidence || []).slice();
      evs.splice(idx, 1);
      saveDraft(ui.date, { evidence: evs });
      render();
      return;
    }

    if (act === 'edit-log') { saveDraft(ui.date, { editing: true }); render(); return; }

    if (act === 'back-today') {
      ui.date = cal.fmt(cal.today());
      ui.quote = '';
      render();
      return;
    }

    if (act === 'jump-date') {
      ui.date = el.dataset.d;
      ui.quote = '';
      VIEW = 'today';
      render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    if (act === 'import-plan') { $('#filePlan').click(); return; }
    if (act === 'import-logs') { $('#fileLogs').click(); return; }
    if (act === 'import-bundle') { $('#fileBundle').click(); return; }
    if (act === 'load-demo') { loadDemo(); return; }

    if (act === 'export-python') { exportForPython(); return; }
    if (act === 'export-bundle') {
      try {
        LM.download('life-mentor-backup-' + cal.fmt(cal.today()) + '.json', store.exportBundle());
        toast('备份已下载');
      } catch (err) { toast(err.message); }
      return;
    }
    if (act === 'export-week') { exportWeekly(); return; }

    if (act === 'reset') {
      if (!confirm('确定清空全部本地数据？此操作不可撤销，建议先导出备份。')) return;
      store.reset();
      ui.date = cal.fmt(cal.today());
      render();
      toast('已清空');
      return;
    }

    if (act === 'set-grace' || act === 'set-carry') {
      var v = Number(el.dataset.v);
      var p = store.profile();
      p.resilience = p.resilience || {};
      if (act === 'set-grace') p.resilience.grace_per_week = v;
      else p.resilience.max_carry_days = v;
      store.saveProfile(p);
      render();
      toast(act === 'set-grace' ? '每周豁免 ' + v + ' 天' : '顺延上限 ' + v + ' 天');
      return;
    }

    if (act === 'set-mot-enabled') {
      var p2 = store.profile();
      p2.motivation = p2.motivation || {};
      p2.motivation.enabled = el.dataset.v === '1';
      store.saveProfile(p2);
      render();
      return;
    }
    if (act === 'set-mot-mode') {
      var p3 = store.profile();
      p3.motivation = p3.motivation || {};
      p3.motivation.mode = el.dataset.v;
      store.saveProfile(p3);
      render();
      toast('文案来源已切换');
      return;
    }
    if (act === 'add-quote') { addQuote(); return; }
    if (act === 'list-quotes') { listQuotes(); return; }
    if (act === 'del-quote') {
      var scene = el.dataset.scene, num = Number(el.dataset.i);
      var p4 = store.profile();
      try { mot.remove(p4, scene, num); store.saveProfile(p4); render(); toast('已删除'); }
      catch (err) { toast(err.message); }
      return;
    }
  }

  function addQuote() {
    var scenes = mot.SCENES.map(function (s, i) { return (i + 1) + '. ' + s + '（' + mot.SCENE_LABEL[s] + '）'; }).join('\n');
    var pick = prompt('这条文案放在哪个场景？输入序号：\n\n' + scenes, '1');
    if (!pick) return;
    var scene = mot.SCENES[Number(pick) - 1];
    if (!scene) { toast('序号不对'); return; }
    var text = prompt('写下你的文案（可以用 {streak} {cumulative} {percent}）：', '');
    if (!text || !text.trim()) return;
    var p = store.profile();
    try {
      mot.add(p, scene, text.trim());
      store.saveProfile(p);
      render();
      toast('已加入「' + mot.SCENE_LABEL[scene] + '」');
    } catch (err) { toast(err.message); }
  }

  function listQuotes() {
    var cfg = mot.config(store.profile());
    var lines = [];
    mot.SCENES.forEach(function (sc) {
      var items = (cfg.custom || {})[sc] || [];
      if (!items.length) return;
      lines.push('【' + mot.SCENE_LABEL[sc] + '】');
      items.forEach(function (t, i) { lines.push('  ' + (i + 1) + '. ' + t); });
    });
    alert(lines.length ? lines.join('\n') : '还没有自定义文案。\n\n点「写一条自己的」加一条，比如：\n「今天不想动，但还是打开了电脑。」');
  }

  /* ------------------------------------------------------------ 导入导出 */
  function readFile(input, cb) {
    var f = input.files && input.files[0];
    if (!f) return;
    var r = new FileReader();
    r.onload = function () { cb(String(r.result || ''), f.name); };
    r.readAsText(f);
    input.value = '';
  }

  function exportForPython() {
    var plan = store.plan();
    if (!plan) { toast('还没有计划'); return; }
    try {
      LM.download((plan.id || 'plan') + '.json', store.exportPlanJson());
      var months = store.exportLogsByMonth();
      var keys = Object.keys(months);
      if (!keys.length) { toast('已导出计划；还没有打卡记录'); return; }
      keys.forEach(function (m, i) {
        setTimeout(function () {
          LM.download(m + '.jsonl', months[m], 'text/plain;charset=utf-8');
        }, 320 * (i + 1));
      });
      LM.download('profile.json', store.exportProfileJson());
      setTimeout(function () {
        toast('已导出 ' + (keys.length + 2) + ' 个文件，放回 .mentor/ 目录即可被 Python 版读取');
      }, 320);
    } catch (err) { toast(err.message); }
  }

  function exportWeekly() {
    var plan = store.plan();
    if (!plan) return;
    var logs = store.latestByDate();
    var ref = cal.today();
    var s = stats.compute(plan, logs, ref, store.profile());
    var w = stats.weekStats(plan, logs, ref);
    var L = [];
    L.push('# ' + w.week + ' 复盘', '');
    L.push('- 目标：' + (plan.goal || ''));
    L.push('- 本周计划 ' + w.planned_days + ' 天，打卡 ' + w.logged_days + ' 天，完成度 ' + pct(w.score) + '%');
    L.push('- 连续打卡 ' + s.streak + ' 天，累计 ' + s.cumulative_days + ' 天，历史最佳 ' + s.best_streak + ' 天');
    L.push('', '## 逐日', '');
    w.rows.forEach(function (r) {
      var st = r.log ? r.log.status : 'missing';
      var lbl = { done: '完成', partial: '部分', skip: '主动跳过', blocked: '受阻', missing: '未打卡' }[st];
      var note = r.log && r.log.note ? ' —— ' + r.log.note : '';
      L.push('- ' + r.date + ' ' + cal.weekdayCn(cal.parseDate(r.date)) + '：' + lbl + note);
    });
    var blocked = [];
    Object.keys(logs).forEach(function (k) {
      if (logs[k].status === 'blocked') blocked.push(logs[k]);
    });
    if (blocked.length) {
      L.push('', '## 卡点', '');
      blocked.slice(-5).forEach(function (b) { L.push('- ' + b.date + '：' + (b.note || '（未填原因）')); });
    }
    L.push('', '## 下一版改什么', '', '- （手动填写：把哪一项任务量调小 / 哪天改成缓冲 / 哪个前置条件要先解决）', '');
    LM.download('review-' + w.week + '.md', L.join('\n'), 'text/markdown;charset=utf-8');
    toast('复盘已下载');
  }

  function loadDemo() {
    var files = ['demo/plan.json', 'demo/logs.jsonl', 'demo/profile.json'];
    Promise.all(files.map(function (f) {
      return fetch(f, { cache: 'no-store' }).then(function (r) {
        if (!r.ok) throw new Error('找不到 ' + f);
        return r.text();
      });
    })).then(function (texts) {
      store.importProfile(JSON.parse(texts[2]));
      store.importPlan(JSON.parse(texts[0]));
      store.importLogs(texts[1]);
      ui.date = cal.fmt(cal.today());
      render();
      toast('已载入示例档案');
    }).catch(function (err) {
      toast('载入失败：' + err.message);
    });
  }

  /* ------------------------------------------------------------ 启动 */
  function init() {
    /* 支持 #/plan #/review #/settings 直达视图；?demo=1 载入示例档案 */
    var params = new URLSearchParams(location.search);
    var hash = location.hash.replace(/^#\//, '');
    if (['today', 'plan', 'review', 'settings'].indexOf(hash) >= 0) VIEW = hash;

    /* 主题 */
    var savedTheme = null;
    try { savedTheme = localStorage.getItem('lm.theme'); } catch (e) {}
    if (savedTheme) document.documentElement.dataset.theme = savedTheme;

    $('#btnTheme').addEventListener('click', function () {
      var cur = document.documentElement.dataset.theme;
      var sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      var next = cur ? (cur === 'dark' ? 'light' : 'dark') : (sysDark ? 'light' : 'dark');
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('lm.theme', next); } catch (e) {}
    });

    /* 标签切换 */
    $('#tabbar').addEventListener('click', function (e) {
      var btn = e.target.closest('[data-tab]');
      if (!btn) return;
      VIEW = btn.dataset.tab;
      if (VIEW === 'today') ui.date = cal.fmt(cal.today());
      render();
      window.scrollTo({ top: 0 });
    });

    document.getElementById('main').addEventListener('click', onMainClick);

    /* 备注输入不重渲染，避免丢焦点 */
    document.getElementById('main').addEventListener('input', function (e) {
      if (e.target && e.target.id === 'noteInput') {
        saveDraft(ui.date, { note: e.target.value });
      }
    });

    /* 文件导入 */
    $('#filePlan').addEventListener('change', function () {
      readFile(this, function (text) {
        try {
          store.importPlan(JSON.parse(text));
          ui.date = cal.fmt(cal.today());
          render();
          toast('计划已导入');
        } catch (err) { toast('导入失败：' + err.message); }
      });
    });

    $('#fileLogs').addEventListener('change', function () {
      readFile(this, function (text) {
        try {
          var n = store.importLogs(text);
          render();
          toast(n ? '新增 ' + n + ' 条打卡记录' : '没有新记录（都已存在）');
        } catch (err) { toast('导入失败：' + err.message); }
      });
    });

    $('#fileBundle').addEventListener('change', function () {
      readFile(this, function (text) {
        try {
          store.importBundle(JSON.parse(text));
          render();
          toast('备份已恢复');
        } catch (err) { toast('恢复失败：' + err.message); }
      });
    });

    $('#fileEvidence').addEventListener('change', function () {
      var files = Array.prototype.slice.call(this.files || []);
      var input = this;
      if (!files.length) return;
      Promise.all(files.map(function (f) {
        if (!/^image\//.test(f.type)) {
          return Promise.resolve({ name: f.name, thumb: '', size: f.size });
        }
        return shrinkImage(f, 520).then(function (thumb) {
          return { name: f.name, thumb: thumb, size: f.size };
        });
      })).then(function (items) {
        var d = getDraft(ui.date);
        var evs = (d.evidence || []).concat(items).slice(0, 6);
        saveDraft(ui.date, { evidence: evs });
        input.value = '';
        render();
        toast('已添加 ' + items.length + ' 个凭证');
      });
    });

    /* 首次打开没计划时，自动尝试载入示例 */
    if (params.has('demo') && !store.hasPlan()) {
      loadDemo();
    }
    render();

    /* 离线可用：只有 https / localhost 才能注册，file:// 打开时跳过 */
    if ('serviceWorker' in navigator && location.protocol !== 'file:') {
      window.addEventListener('load', function () {
        navigator.serviceWorker.register('./sw.js').catch(function () { /* 忽略，不影响使用 */ });
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
