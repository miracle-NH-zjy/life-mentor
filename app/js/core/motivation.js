/* 文案层：与 scripts/lib/motivation.py 同一套内置语料与选取规则。
 *
 * 约束：
 * · 内置文案必须有信息，不能是「加油你一定行」这类空话
 * · 用户可追加自己的文案，或切换成「只用自己写的」
 * · 同一场景短期不重复（记住最近用过的，从候选里剔除）
 * · 支持占位符 {days} {streak} {cumulative} {percent} {rate} {name}
 */
(function (global) {
  'use strict';
  var LM = global.LM || (global.LM = {});

  var SCENES = ['done', 'recovery', 'milestone', 'low', 'blocked', 'skip'];
  var SCENE_LABEL = {
    done: '打卡完成',
    recovery: '断签后恢复',
    milestone: '里程碑',
    low: '低谷',
    blocked: '受阻',
    skip: '主动休息'
  };

  var BUILTIN = {
    done: [
      '做完了。今天这一格是真的。',
      '完成本身就是证据——证明这件事在你的掌控里。',
      '不需要感动，记下来就行。{streak} 天了。',
      '今天的进度条往前挪了一点，这就够了。',
      '做完比做完美重要。你今天赢了这一回合。',
      '这一项进了账，它不会因为你某天没做而消失。',
      '记下来了。明天的事明天再说。',
      '你今天没有和自己讨价还价——这比任务本身更难。'
    ],
    recovery: [
      '断了几天，又回来了。回来这件事比从不中断更稀有。',
      '重新开始不需要仪式。你刚才就已经开始了。',
      '中断过的人才知道怎么接着往下走。今天的 {streak} 天算数。',
      '之前的记录还在，没有作废。你不是从零开始，是从 {cumulative} 继续。',
      '断一次不等于失败，断完不回来才算。你回来了。'
    ],
    milestone: [
      '{cumulative} 天了。这个数字本身没有魔力，但它说明你能稳定地做一件事。',
      '已经走了 {percent}% 的路。回头看，这段时间你没在原地打转。',
      '连续 {streak} 天——不是靠意志力，是靠你已经把它变成了日常。',
      '{cumulative} 天。当初那个「我大概坚持不下来」的判断，正在被推翻。'
    ],
    low: [
      '完成率低不代表你不行，只代表这个计划定得比现实重。该调的是计划。',
      '今天没做到，不代表明天也做不到。这两件事之间没有因果关系。',
      '现在的数字不好看，但它至少是真实的。真实的数字才能改。',
      '先别谈坚持，先谈能不能明天打开它一次。',
      '你在硬扛一个不匹配的计划。这不是你的错，但改变它是你的责任。'
    ],
    blocked: [
      '被挡住了就记下来，这比硬撑有用。原因写清楚，下一版计划才有依据。',
      '受阻不是断签。你已经如实上报了，这就是在做正确的事。',
      '环境不配合的时候，改环境，别改自己。'
    ],
    skip: [
      '主动休息也是计划的一部分。你今天做了选择，不是逃避。',
      '停下来一天不会让前面的努力消失，连续 {streak} 天还在。',
      '会休息的人才跑得远。明天见。'
    ]
  };

  var DEFAULTS = { enabled: true, mode: 'mix', custom: {}, recent: 4 };

  function config(state) {
    var cfg = Object.assign({}, DEFAULTS);
    if (state && state.motivation) Object.assign(cfg, state.motivation);
    if (!cfg.custom) cfg.custom = {};
    return cfg;
  }

  function candidates(state, scene) {
    var cfg = config(state);
    var custom = (cfg.custom || {})[scene] || [];
    if (cfg.mode === 'custom') return custom.slice();
    if (cfg.mode === 'builtin') return (BUILTIN[scene] || []).slice();
    return (BUILTIN[scene] || []).concat(custom);
  }

  function renderText(template, ctx) {
    return String(template).replace(/\{(\w+)\}/g, function (m, k) {
      return ctx[k] != null ? String(ctx[k]) : m;
    });
  }

  function pick(state, scene, ctx, recentLog) {
    var cfg = config(state);
    if (!cfg.enabled) return '';
    var pool = candidates(state, scene);
    if (!pool.length) return '';
    var avoid = (recentLog || []).slice();
    var fresh = pool.filter(function (t) { return avoid.indexOf(t) < 0; });
    var chosen = (fresh.length ? fresh : pool)[Math.floor(Math.random() * (fresh.length ? fresh.length : pool.length))];
    return renderText(chosen, ctx || {});
  }

  function add(state, scene, text) {
    if (SCENES.indexOf(scene) < 0) throw new Error('未知场景：' + scene);
    var cfg = config(state);
    var custom = {};
    Object.keys(cfg.custom || {}).forEach(function (k) { custom[k] = cfg.custom[k].slice(); });
    var items = (custom[scene] || []).slice();
    if (items.indexOf(text) >= 0) throw new Error('这条文案已经存在了');
    items.push(text);
    custom[scene] = items;
    cfg.custom = custom;
    state.motivation = cfg;
    return cfg;
  }

  function remove(state, scene, index) {
    var cfg = config(state);
    var custom = {};
    Object.keys(cfg.custom || {}).forEach(function (k) { custom[k] = cfg.custom[k].slice(); });
    var items = (custom[scene] || []).slice();
    if (index < 1 || index > items.length) throw new Error('序号超出范围');
    var removed = items.splice(index - 1, 1)[0];
    custom[scene] = items;
    cfg.custom = custom;
    state.motivation = cfg;
    return removed;
  }

  LM.motivation = {
    SCENES: SCENES,
    SCENE_LABEL: SCENE_LABEL,
    BUILTIN: BUILTIN,
    DEFAULTS: DEFAULTS,
    config: config,
    candidates: candidates,
    renderText: renderText,
    pick: pick,
    add: add,
    remove: remove
  };
})(window);
