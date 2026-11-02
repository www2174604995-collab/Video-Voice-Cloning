/* Page glue: floating panel, subtitle overlay, player clock, message routing. */
(function () {
  'use strict';
  if (window.__BSP_CONTENT__) return;
  window.__BSP_CONTENT__ = true;

  var DEFAULTS = {
    target: 'en',
    voice: 'clone',
    orig: 0.12,
    tts: 1.0,
    subs: true,
    server: 'ws://127.0.0.1:8765/ws'
  };

  var st = {
    settings: Object.assign({}, DEFAULTS),
    running: false,
    video: null,
    panel: null,
    subsEl: null,
    delay: 3.0,
    subs: [],
    shownId: -1,
    passthrough: false,
    lastTime: 0,
    lastAt: 0,
    mounted: false
  };

  function send(msg) {
    try {
      var p = chrome.runtime.sendMessage(msg);
      if (p && p.catch) p = p.catch(function () { return null; });
      return p || Promise.resolve(null);
    } catch (e) {
      return Promise.resolve(null);
    }
  }

  function toOffscreen(msg) {
    msg.to = 'offscreen';
    return send(msg);
  }

  /* ---------------- storage ---------------- */

  function loadSettings() {
    try {
      chrome.storage.local.get('bilisimul', function (data) {
        var saved = (data && data.bilisimul) || {};
        st.settings = Object.assign({}, DEFAULTS, saved);
        if (st.panel) applySettingsToPanel();
      });
    } catch (e) { /* ignore */ }
  }

  function saveSettings() {
    try { chrome.storage.local.set({ bilisimul: st.settings }); } catch (e) { /* ignore */ }
  }

  function applySettingsToPanel() {
    // panel reads its own inputs; nothing to do unless we reload the page
  }

  /* ---------------- video discovery ---------------- */

  function pickVideo() {
    var nodes = document.querySelectorAll('video, bwp-video');
    var fallback = null;
    for (var i = 0; i < nodes.length; i++) {
      var v = nodes[i];
      if (typeof v.currentTime !== 'number') continue;
      var r = v.getBoundingClientRect();
      if (r.width > 320 && r.height > 180) return v;
      if (!fallback) fallback = v;
    }
    return fallback;
  }

  function isSupportedPage() {
    var p = location.pathname;
    return p.indexOf('/video/') === 0 || p.indexOf('/bangumi/play/') === 0 ||
      p.indexOf('/list/') === 0 || p.indexOf('/cheese/play/') === 0 ||
      p.indexOf('/festival/') === 0 || p.indexOf('/medialist/') === 0;
  }

  /* ---------------- UI ---------------- */

  function mount() {
    if (st.mounted || !window.BSP_UI) return;
    st.mounted = true;
    st.panel = window.BSP_UI.createPanel({
      initial: st.settings,
      onStart: startTranslation,
      onStop: stopTranslation,
      onConfig: onConfigChanged,
      onVolume: onVolumeChanged
    });
    document.documentElement.appendChild(st.panel.host);
    st.subsEl = window.BSP_UI.createSubtitles();
    document.documentElement.appendChild(st.subsEl.host);
    if (!isSupportedPage()) {
      st.panel.setHint('当前页面可能不是视频页：面板会一直待命。');
    }
  }

  function unmount() {
    if (st.panel) { st.panel.host.remove(); st.panel = null; }
    if (st.subsEl) { st.subsEl.host.remove(); st.subsEl = null; }
    st.mounted = false;
  }

  function onConfigChanged(cfg) {
    st.settings = Object.assign(st.settings, cfg);
    st.delay = st.delay;
    saveSettings();
    if (st.running) {
      toOffscreen({ type: 'config', config: { target: cfg.target, voice: cfg.voice, server: cfg.server } });
    }
    if (!cfg.subs && st.subsEl) st.subsEl.hide(true);
  }

  function onVolumeChanged(cfg) {
    st.settings = Object.assign(st.settings, cfg);
    saveSettings();
    if (st.running) toOffscreen({ type: 'volumes', orig: cfg.orig, tts: cfg.tts });
  }

  /* ---------------- start / stop ---------------- */

  async function startTranslation(cfg) {
    if (!st.video) {
      st.panel.toast('这个页面还没找到播放器，先播放视频再试。');
      return;
    }
    st.settings = Object.assign(st.settings, cfg);
    saveSettings();
    st.panel.setStatus('正在接管声音…', 'busy');
    st.panel.setHint('');
    var res = await send({ to: 'bg', type: 'start', config: st.settings });
    if (!res || !res.ok) {
      if (res && res.code === 'gesture') {
        st.panel.setStatus('等待授权', 'err');
        st.panel.toast('Chrome 要求这次授权由你亲自点一下：点击浏览器右上角工具栏里的插件图标即可开始（之后本页再开无需重复）。', 9000);
      } else {
        st.panel.flashError((res && res.message) || '启动失败，请确认服务端已运行。');
      }
      return;
    }
    setRunning(true);
    st.panel.setStatus('已接管 · 等待声音', 'busy');
  }

  async function stopTranslation() {
    await send({ to: 'bg', type: 'stop' });
    setRunning(false);
    st.panel.setStatus('B站同声传译');
    st.panel.setHint('');
    st.passthrough = false;
    st.subs = [];
    if (st.subsEl) st.subsEl.hide(true);
  }

  function setRunning(running) {
    st.running = !!running;
    if (st.panel) st.panel.setRunning(st.running);
  }

  /* ---------------- clock ---------------- */

  function tick() {
    if (!st.video) return;
    var v = st.video;
    var now = performance.now();
    if (st.running) {
      var jump = Math.abs(v.currentTime - st.lastTime) > 1.1 && (now - st.lastAt) < 900;
      if (jump) {
        st.subs = [];
        toOffscreen({ type: 'resync' });
        if (st.subsEl) st.subsEl.hide(true);
        st.shownId = -1;
      }
      st.lastTime = v.currentTime;
      st.lastAt = now;
      toOffscreen({
        type: 'tick',
        t: v.currentTime,
        paused: v.paused,
        rate: v.playbackRate || 1
      });
    }
  }

  function renderSubs() {
    if (!st.subsEl || !st.video) return;
    if (!st.settings.subs) { st.subsEl.hide(true); return; }
    var vt = st.video.currentTime;
    var d = st.delay;
    var active = null;
    for (var i = st.subs.length - 1; i >= 0; i--) {
      var s = st.subs[i];
      if (vt < s.t0 + d - 14) { st.subs.splice(i, 1); continue; }
      if (vt >= s.t0 + d - 0.25 && vt <= s.t1 + d + 1.3) { active = s; break; }
    }
    if (active) {
      if (active.id !== st.shownId) {
        st.subsEl.show(active.src, active.dst);
        st.shownId = active.id;
      }
    } else if (st.shownId !== -1) {
      st.subsEl.hide();
      st.shownId = -1;
    }
  }

  /* ---------------- messages from the engine ---------------- */

  function onEngineMessage(msg) {
    switch (msg.type) {
      case 'started':
        setRunning(true);
        if (st.panel) st.panel.setStatus('已接管 · 等待声音', 'busy');
        toOffscreen({ type: 'config', config: { target: st.settings.target, voice: st.settings.voice, server: st.settings.server } });
        break;
      case 'stopped':
        setRunning(false);
        if (st.panel) st.panel.setStatus('已停止');
        break;
      case 'need-gesture':
        setRunning(false);
        if (st.panel) {
          st.panel.setStatus('等待授权', 'err');
          st.panel.toast('请点击浏览器工具栏的插件图标完成授权。', 6000);
        }
        break;
      case 'status':
        if (!st.panel) break;
        if (msg.status === 'online') st.panel.setStatus('引擎已连接 · 听声音中', 'busy');
        else if (msg.status === 'offline') st.panel.setStatus('引擎断开，重连中', 'busy');
        else if (msg.status === 'error') st.panel.setStatus('引擎连接失败', 'err');
        break;
      case 'ready':
        onReady(msg);
        break;
      case 'subtitle':
        st.subs.push(msg);
        if (st.subs.length > 12) st.subs.shift();
        break;
      case 'stat':
        if (st.panel) st.panel.setStats(msg);
        if (isFinite(msg.delay)) {
          st.delay = msg.delay;
          if (st.panel) st.panel.setDelay(msg.delay);
        }
        break;
      case 'delay':
        if (isFinite(msg.value)) {
          st.delay = msg.value;
          if (st.panel) st.panel.setDelay(msg.value);
        }
        break;
      case 'passthrough':
        st.passthrough = !!msg.on;
        if (st.panel) {
          st.panel.setHint(msg.on
            ? '这段视频本来就说目标语言，已经恢复原声、只保留字幕。'
            : '');
        }
        break;
      case 'error':
        if (st.panel) st.panel.flashError(msg.message || '引擎报错');
        break;
      case 'diag':
        if (st.panel) {
          var d = msg;
          var warn = (d.chunks === 0) ? ' ⚠无采集' : '';
          st.panel.setDiag('采集 ' + d.chunks + '/3s · 播放 ' + d.played + ' · 丢 ' + d.dropped + ' · ' + d.ctx + warn);
          if (d.delay) st.panel.setDelay(d.delay);
        }
        break;
      case 'drop':
        if (st.panel) {
          st.panel.setHint('配音引擎跟不上，丢掉了一段（延迟 ' + Math.round(msg.late) + 's）。换成 --tts sapi 会跟手很多。');
        }
        break;
      default:
        break;
    }
  }

  function onReady(msg) {
    if (!st.panel) return;
    var b = msg.backends || {};
    var parts = [];
    if (b.asr) parts.push('识别 ' + b.asr);
    if (b.mt) parts.push('翻译 ' + b.mt);
    if (b.tts) parts.push('配音 ' + b.tts);
    st.panel.setHint(parts.join(' · '));
    if (st.settings.voice === 'clone' && b.supports_clone === false) {
      st.panel.toast('当前配音引擎（' + b.tts + '）不支持音色克隆，将使用固定音色。想要原声线请切换 xtts / cosyvoice 引擎。', 8000);
    }
  }

  try {
    chrome.runtime.onMessage.addListener(function (msg) {
      if (!msg || msg.to !== 'content') return;
      onEngineMessage(msg);
    });
  } catch (e) { /* ignore */ }

  /* ---------------- loops ---------------- */

  setInterval(function () {
    var v = pickVideo();
    if (v !== st.video) {
      st.video = v;
      st.subs = [];
      st.shownId = -1;
    }
    if (v && !st.mounted) mount();
  }, 900);

  setInterval(tick, 250);
  setInterval(renderSubs, 110);

  loadSettings();
  var firstVideo = pickVideo();
  if (firstVideo) {
    st.video = firstVideo;
    mount();
  }

  // exposed only inside this isolated world; handy for debugging on the page
  window.__bspDebug = st;

  window.addEventListener('pagehide', function () {
    if (st.running) send({ to: 'bg', type: 'stop' });
  });
})();
