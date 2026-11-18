/* 日期层：与 scripts/lib/cal.py 行为一一对应。
 * 所有日期只做「天」粒度运算，用本地时区构造，避免 UTC 偏移导致跨天错位。 */
(function (global) {
  'use strict';
  var LM = global.LM || (global.LM = {});

  var WEEKDAY_CN = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  var DEFAULT_BUFFER_WEEKDAY = 6; // Python weekday: 周日 = 6

  function parseDate(s) {
    if (s instanceof Date) return new Date(s.getFullYear(), s.getMonth(), s.getDate());
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || '').trim());
    if (!m) throw new Error('日期格式不对：' + s + '，应为 YYYY-MM-DD');
    return new Date(+m[1], +m[2] - 1, +m[3]);
  }

  function fmt(d) {
    var m = d.getMonth() + 1, day = d.getDate();
    return d.getFullYear() + '-' + (m < 10 ? '0' : '') + m + '-' + (day < 10 ? '0' : '') + day;
  }

  function addDays(d, n) {
    var x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() + n);
    return x;
  }

  function diffDays(a, b) {
    var ms = parseDate(b).getTime() - parseDate(a).getTime();
    return Math.round(ms / 86400000);
  }

  function dateRange(start, end) {
    var s = parseDate(start), e = parseDate(end);
    if (e < s) throw new Error('结束日期 ' + fmt(e) + ' 早于开始日期 ' + fmt(s));
    var out = [], cur = s;
    while (cur <= e) { out.push(cur); cur = addDays(cur, 1); }
    return out;
  }

  /* Python weekday: 周一 = 0 ... 周日 = 6 */
  function pyWeekday(d) { return (d.getDay() + 6) % 7; }

  function weekdayCn(d) { return WEEKDAY_CN[d.getDay()]; }

  /* ISO 8601 周编号，与 Python date.isocalendar() 一致 */
  function weekKey(d) {
    var t = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var dow = (t.getDay() + 6) % 7;
    t.setDate(t.getDate() - dow + 3);            // 移到本周四
    var year = t.getFullYear();
    var jan4 = new Date(year, 0, 4);
    var jdow = (jan4.getDay() + 6) % 7;
    var week1Thu = addDays(jan4, 3 - jdow);
    var week = 1 + Math.round((t.getTime() - week1Thu.getTime()) / 604800000);
    return year + '-W' + (week < 10 ? '0' : '') + week;
  }

  function weekBounds(d) {
    var monday = addDays(d, -pyWeekday(d));
    return { start: monday, end: addDays(monday, 6) };
  }

  function phaseFor(d, phases) {
    for (var i = 0; i < (phases || []).length; i++) {
      var ph = phases[i];
      if (parseDate(ph.start) <= d && d <= parseDate(ph.end)) return ph.name || '';
    }
    return '';
  }

  function dayIndex(d, start) { return diffDays(start, d) + 1; }

  function isBufferDay(d, plan) {
    var list = (plan && plan.buffer_days) || [];
    if (list.indexOf(fmt(d)) >= 0) return true;
    var bw = plan && plan.buffer_weekday != null ? +plan.buffer_weekday : DEFAULT_BUFFER_WEEKDAY;
    return pyWeekday(d) === bw;
  }

  function today() {
    var n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), n.getDate());
  }

  function nowIso() {
    var n = new Date(), p = function (x) { return (x < 10 ? '0' : '') + x; };
    return n.getFullYear() + '-' + p(n.getMonth() + 1) + '-' + p(n.getDate()) +
      'T' + p(n.getHours()) + ':' + p(n.getMinutes()) + ':' + p(n.getSeconds());
  }

  function cnDate(d) {
    return (d.getMonth() + 1) + ' 月 ' + d.getDate() + ' 日';
  }

  LM.cal = {
    WEEKDAY_CN: WEEKDAY_CN,
    parseDate: parseDate,
    fmt: fmt,
    addDays: addDays,
    diffDays: diffDays,
    dateRange: dateRange,
    pyWeekday: pyWeekday,
    weekdayCn: weekdayCn,
    weekKey: weekKey,
    weekBounds: weekBounds,
    phaseFor: phaseFor,
    dayIndex: dayIndex,
    isBufferDay: isBufferDay,
    today: today,
    nowIso: nowIso,
    cnDate: cnDate
  };
})(window);
