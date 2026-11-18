/* 数据层：localStorage 持久化 + 与 Python 版 .mentor/ 目录的双向互通。
 *
 * 存储键：
 *   lm.profile  profile.json 的镜像（含 resilience / motivation 配置）
 *   lm.plan     当前计划，字段与 plans/<plan-id>.json 完全一致
 *   lm.logs     打卡流水数组，等价于 logs/YYYY-MM.jsonl 的全部行
 *   lm.state    文案去重状态等运行期数据
 */
(function (global) {
  'use strict';
  var LM = global.LM || (global.LM = {});
  var cal = LM.cal;

  var KEYS = { profile: 'lm.profile', plan: 'lm.plan', logs: 'lm.logs', state: 'lm.state' };

  function safeGet(key, fallback) {
    try {
      var raw = global.localStorage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch (e) {
      console.warn('读取本地数据失败', key, e);
      return fallback;
    }
  }

  function safeSet(key, value) {
    try {
      global.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      if (e && e.name === 'QuotaExceededError') {
        throw new Error('本地存储已满。请在「设置」里导出备份后清理旧凭证图片。');
      }
      throw e;
    }
  }

  var store = {
    KEYS: KEYS,

    profile: function () {
      return safeGet(KEYS.profile, { schema: 1, name: '', goal: {}, constraints: {}, motivation: {}, resilience: {} });
    },
    saveProfile: function (p) {
      p.updated_at = cal.nowIso();
      safeSet(KEYS.profile, p);
      return p;
    },

    plan: function () { return safeGet(KEYS.plan, null); },
    savePlan: function (p) { safeSet(KEYS.plan, p); return p; },
    hasPlan: function () { return !!safeGet(KEYS.plan, null); },

    logs: function () { return safeGet(KEYS.logs, []); },
    saveLogs: function (l) { safeSet(KEYS.logs, l); return l; },

    state: function () { return safeGet(KEYS.state, { recentQuotes: [] }); },
    saveState: function (s) { safeSet(KEYS.state, s); return s; },

    /* 每个日期只取最后一条，与 Python 版 latest_logs_by_date 一致 */
    latestByDate: function () {
      var out = {};
      this.logs().forEach(function (e) {
        if (e && e.date) out[e.date] = e;
      });
      return out;
    },

    appendLog: function (record) {
      var logs = this.logs();
      logs.push(record);
      this.saveLogs(logs);
      return record;
    },

    /* 忘记打卡不算失败：补录时覆盖当天状态即可，流水仍然保留 */
    todayLog: function (dateKey) {
      return this.latestByDate()[dateKey] || null;
    },

    rememberQuote: function (text) {
      var st = this.state();
      st.recentQuotes = (st.recentQuotes || []).concat([text]).slice(-6);
      this.saveState(st);
    },

    /* ---------------- 导入 ---------------- */

    importPlan: function (obj) {
      if (!obj || !obj.days || !obj.start_date || !obj.end_date) {
        throw new Error('这不是有效的计划文件：缺少 days / start_date / end_date');
      }
      obj.days.forEach(function (d) {
        if (!d.date) throw new Error('计划里有日期为空的任务组');
        (d.tasks || []).forEach(function (t, i) {
          if (!t.id) t.id = d.date.replace(/-/g, '').slice(2) + 't' + (i + 1);
        });
      });
      obj.id = obj.id || ('plan-' + obj.start_date.slice(0, 7));
      this.savePlan(obj);
      return obj;
    },

    /* 支持 .jsonl（每行一条）与 .json（数组）两种格式 */
    importLogs: function (text) {
      var trimmed = String(text || '').trim();
      if (!trimmed) throw new Error('文件是空的');
      var rows = [];
      if (trimmed.charAt(0) === '[') {
        rows = JSON.parse(trimmed);
      } else {
        trimmed.split(/\r?\n/).forEach(function (line, i) {
          if (!line.trim()) return;
          try { rows.push(JSON.parse(line)); }
          catch (e) { throw new Error('第 ' + (i + 1) + ' 行不是合法 JSON'); }
        });
      }
      if (!Array.isArray(rows)) throw new Error('打卡文件的格式不对');
      rows.forEach(function (r) {
        if (!r || !r.date) throw new Error('有一条打卡记录缺少 date 字段');
      });
      var existing = this.logs();
      var seen = {};
      existing.forEach(function (e, i) {
        seen[e.date + '@' + (e.at || '')] = true;
      });
      var added = 0;
      rows.forEach(function (r) {
        var k = r.date + '@' + (r.at || '');
        if (seen[k]) return;
        seen[k] = true;
        existing.push(r);
        added += 1;
      });
      existing.sort(function (a, b) { return (a.date + (a.at || '')).localeCompare(b.date + (b.at || '')); });
      this.saveLogs(existing);
      return added;
    },

    importProfile: function (obj) {
      if (!obj || typeof obj !== 'object') throw new Error('档案文件格式不对');
      var cur = this.profile();
      Object.assign(cur, obj);
      this.saveProfile(cur);
      return cur;
    },

    /* ---------------- 导出 ---------------- */

    exportPlanJson: function () {
      var p = this.plan();
      if (!p) throw new Error('还没有计划可以导出');
      return JSON.stringify(p, null, 2);
    },

    /* 按 Python 版命名规则输出 logs/YYYY-MM.jsonl 的文本 */
    exportLogsByMonth: function () {
      var groups = {};
      this.logs().forEach(function (e) {
        var m = e.date.slice(0, 7);
        (groups[m] || (groups[m] = [])).push(e);
      });
      var out = {};
      Object.keys(groups).sort().forEach(function (m) {
        out[m] = groups[m].map(function (e) { return JSON.stringify(e); }).join('\n') + '\n';
      });
      return out;
    },

    exportProfileJson: function () {
      return JSON.stringify(this.profile(), null, 2);
    },

    exportBundle: function () {
      return JSON.stringify({
        kind: 'life-mentor-backup',
        version: 1,
        exported_at: cal.nowIso(),
        profile: this.profile(),
        plan: this.plan(),
        logs: this.logs(),
        state: this.state()
      }, null, 2);
    },

    importBundle: function (obj) {
      if (!obj || obj.kind !== 'life-mentor-backup') throw new Error('这不是 life-mentor 的备份文件');
      if (obj.profile) safeSet(KEYS.profile, obj.profile);
      if (obj.plan) safeSet(KEYS.plan, obj.plan);
      if (obj.logs) safeSet(KEYS.logs, obj.logs);
      if (obj.state) safeSet(KEYS.state, obj.state);
      return true;
    },

    reset: function () {
      [KEYS.profile, KEYS.plan, KEYS.logs, KEYS.state].forEach(function (k) {
        global.localStorage.removeItem(k);
      });
    }
  };

  /* ---------------- 文件下载 ---------------- */
  function download(filename, text, mime) {
    var blob = new Blob([text], { type: mime || 'application/json;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  LM.store = store;
  LM.download = download;
})(window);
