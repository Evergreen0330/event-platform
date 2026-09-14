// 自检站主逻辑：hash 路由 + seed.json 网络加载 + 离线降级
// 全部使用相对路径，保证在 /<repo>/ 子路径下可用

(function () {
  'use strict';

  var PROBE = [];
  function record(key, ok, detail) {
    PROBE.push({ key: key, ok: ok, detail: detail });
  }

  // ---- 1. 路由 ----
  var ROUTES = ['#/home', '#/probe'];

  function currentRoute() {
    var h = location.hash || '#/home';
    return ROUTES.indexOf(h) >= 0 ? h : '#/home';
  }

  function render() {
    var route = currentRoute();
    var home = document.getElementById('view-home');
    var probe = document.getElementById('view-probe');
    if (!home || !probe) return;
    home.hidden = route !== '#/home';
    probe.hidden = route !== '#/probe';
    if (route === '#/probe') renderProbe();
  }

  window.addEventListener('hashchange', render);

  // ---- 2. 数据加载 + 离线降级 ----
  var FALLBACK = [{ id: 1, name: '离线种子数据', source: 'builtin-fallback' }];
  var dataState = { loaded: false, source: null, rows: 0 };

  function loadSeed() {
    return fetch('assets/data/seed.json', { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (json) {
        dataState.loaded = true;
        dataState.source = 'network';
        dataState.rows = (json.items || []).length;
        return json;
      })
      .catch(function (e) {
        dataState.loaded = false;
        dataState.source = 'builtin-fallback (' + e.message + ')';
        dataState.rows = FALLBACK.length;
        return { items: FALLBACK };
      });
  }

  // ---- 3. 自检面板 ----
  function renderProbe() {
    var tbody = document.querySelector('#probe-table tbody');
    if (!tbody) return;

    var rows = PROBE.concat([
      {
        key: 'JS 已执行',
        ok: true,
        detail: 'app.js 运行到渲染阶段'
      },
      {
        key: '当前 hash 路由',
        ok: ROUTES.indexOf(location.hash) >= 0,
        detail: location.hash || '(空，回退 #/home)'
      },
      {
        key: '部署基路径 location.pathname',
        ok: true,
        detail: location.pathname
      },
      {
        key: 'seed.json 数据来源',
        ok: true,
        detail: dataState.source + '（' + dataState.rows + ' 条）'
      },
      {
        key: 'jsdom/canvas 无关：纯 DOM 渲染',
        ok: !!document.body,
        detail: 'body 存在，DOM 可用'
      }
    ]);

    var html = '';
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      html += '<tr><td class="k">' + esc(r.key) + '</td><td class="' +
        (r.ok ? 'ok' : 'bad') + '">' + (r.ok ? 'PASS' : 'FAIL') +
        '</td><td>' + esc(String(r.detail)) + '</td></tr>';
    }
    tbody.innerHTML = html;
  }

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ---- 启动 ----
  var stamp = document.getElementById('build-stamp');
  if (stamp) stamp.textContent = 'selftest v2 · API 兜底验证 · ' + location.pathname;

  loadSeed().then(function () {
    record('seed.json 网络请求', dataState.source === 'network',
      dataState.source === 'network' ? '从 assets/data/seed.json 取到' : '已降级：' + dataState.source);
    renderProbe();
    render();
  });

  // 供自动化读取
  window.__SELFTEST__ = {
    probe: PROBE,
    dataState: dataState,
    route: currentRoute()
  };
})();
