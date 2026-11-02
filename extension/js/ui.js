(function (global) {
  'use strict';

  var LANGS = [
    { code: 'en', label: 'English 英语' },
    { code: 'zh', label: '中文' },
    { code: 'ja', label: '日本語 日语' },
    { code: 'ko', label: '한국어 韩语' },
    { code: 'es', label: 'Español 西语' },
    { code: 'fr', label: 'Français 法语' },
    { code: 'de', label: 'Deutsch 德语' },
    { code: 'ru', label: 'Русский 俄语' },
    { code: 'pt', label: 'Português 葡语' },
    { code: 'it', label: 'Italiano 意语' },
    { code: 'ar', label: 'العربية 阿语' },
    { code: 'hi', label: 'हिन्दी 印地语' },
    { code: 'th', label: 'ไทย 泰语' },
    { code: 'vi', label: 'Tiếng Việt 越南语' },
    { code: 'id', label: 'Indonesia 印尼语' }
  ];

  var CSS = ":host { all: initial; }\n:host, * { box-sizing: border-box; }\n.panel { width: 264px; font-family: \"PingFang SC\", \"Microsoft YaHei\", system-ui, -apple-system, sans-serif;\n  color: #e9e9ef; background: rgba(22,22,27,.94); border: 1px solid rgba(255,255,255,.09);\n  border-radius: 14px; box-shadow: 0 12px 34px rgba(0,0,0,.45), 0 1px 0 rgba(255,255,255,.05) inset;\n  backdrop-filter: blur(14px); overflow: hidden; user-select: none; }\n.head { display: flex; align-items: center; gap: 8px; padding: 10px 12px; cursor: default; }\n.logo { width: 22px; height: 22px; border-radius: 7px; display: flex; align-items: center; justify-content: center;\n  font-size: 13px; font-weight: 700; color: #fff; background: linear-gradient(135deg,#fb7299,#ff9db4); flex: none; }\n.title { font-size: 13px; font-weight: 600; letter-spacing: .3px; flex: 1; }\n.dot { width: 7px; height: 7px; border-radius: 50%; background: #6b6b76; flex: none; transition: background .2s; }\n.dot.on { background: #31c48d; box-shadow: 0 0 0 0 rgba(49,196,141,.55); animation: pulse 2s infinite; }\n.dot.busy { background: #f5a524; animation: pulse 1s infinite; }\n.dot.err { background: #ef4444; }\n@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(49,196,141,.5); } 70% { box-shadow: 0 0 0 6px rgba(49,196,141,0); } 100% { box-shadow: 0 0 0 0 rgba(49,196,141,0); } }\n.icon-btn { width: 22px; height: 22px; border: 0; border-radius: 6px; background: transparent; color: #a4a4b0;\n  cursor: pointer; font-size: 15px; line-height: 1; display: flex; align-items: center; justify-content: center; }\n.icon-btn:hover { background: rgba(255,255,255,.09); color: #fff; }\n.body { padding: 2px 12px 12px; display: block; }\n.panel.min .body { display: none; }\n.field { display: flex; align-items: center; gap: 8px; margin: 9px 0; font-size: 12px; }\n.field > label { width: 58px; color: #9a9aa6; flex: none; }\n.field select, .field input[type=\"text\"] { flex: 1; min-width: 0; height: 26px; border-radius: 7px;\n  border: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.05); color: #e9e9ef;\n  font-size: 12px; padding: 0 8px; outline: none; font-family: inherit; }\n.field select:focus, .field input[type=\"text\"]:focus { border-color: rgba(251,114,153,.65); }\n.field select option { background: #212127; color: #e9e9ef; }\n.range { flex: 1; display: flex; align-items: center; gap: 8px; }\ninput[type=\"range\"] { flex: 1; -webkit-appearance: none; appearance: none; height: 3px; border-radius: 2px;\n  background: rgba(255,255,255,.16); outline: none; }\ninput[type=\"range\"]::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%;\n  background: #fb7299; cursor: pointer; box-shadow: 0 0 0 3px rgba(251,114,153,.16); }\n.val { width: 34px; text-align: right; color: #b9b9c6; font-variant-numeric: tabular-nums; font-size: 11px; }\n.switch { position: relative; width: 34px; height: 19px; border-radius: 10px; background: rgba(255,255,255,.14);\n  cursor: pointer; transition: background .18s; flex: none; margin-left: auto; }\n.switch.on { background: #fb7299; }\n.switch i { position: absolute; top: 2px; left: 2px; width: 15px; height: 15px; border-radius: 50%; background: #fff;\n  transition: transform .18s; }\n.switch.on i { transform: translateX(15px); }\n.meta { display: flex; gap: 6px; flex-wrap: wrap; margin: 10px 0 4px; min-height: 18px; }\n.chip { font-size: 10px; padding: 2px 7px; border-radius: 999px; background: rgba(255,255,255,.07);\n  color: #9a9aa6; font-variant-numeric: tabular-nums; }\n.chip b { color: #cfcfda; font-weight: 600; }\n.run { width: 100%; height: 34px; margin-top: 8px; border: 0; border-radius: 9px; cursor: pointer;\n  font-size: 13px; font-weight: 600; color: #fff; font-family: inherit;\n  background: linear-gradient(135deg,#fb7299,#ff8fab); transition: filter .15s, transform .06s; }\n.run:hover { filter: brightness(1.06); }\n.run:active { transform: translateY(1px); }\n.run.stop { background: linear-gradient(135deg,#4b4b57,#5d5d6b); }\n.hint { font-size: 10.5px; color: #8b8b98; margin-top: 8px; line-height: 1.5; }\n.hint b { color: #d7a5b5; font-weight: 600; }\n.toast { position: fixed; left: 50%; top: 76px; transform: translateX(-50%); max-width: 360px;\n  background: rgba(28,28,34,.96); border: 1px solid rgba(255,255,255,.1); color: #f0f0f5;\n  font-size: 12.5px; line-height: 1.5; padding: 9px 14px; border-radius: 10px; box-shadow: 0 8px 26px rgba(0,0,0,.4);\n  opacity: 0; transition: opacity .2s, transform .2s; pointer-events: none; }\n.toast.show { opacity: 1; transform: translateX(-50%) translateY(2px); }";

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function createPanel(opts) {
    opts = opts || {};
    var initial = opts.initial || {};
    var host = el('div');
    host.id = 'bsp-panel-host';
    host.style.cssText = 'position:fixed;top:96px;right:16px;z-index:2147483000;';
    var root = host.attachShadow({ mode: 'open' });
    var style = el('style');
    style.textContent = CSS + ".sub{font-size:11px;color:#8d8d9b;margin:-2px 0 7px;line-height:1.4;}.sub.busy{color:#f5a524}.sub.on{color:#31c48d}.sub.err{color:#ef4444}";
    root.appendChild(style);

    var panel = el('div', 'panel');
    var head = el('div', 'head');
    var logo = el('div', 'logo', '译');
    var title = el('div', 'title', 'B站同声传译');
    var dot = el('div', 'dot');
    var minBtn = el('button', 'icon-btn', '–');
    minBtn.title = '收起 / 展开';
    head.appendChild(logo); head.appendChild(title); head.appendChild(dot); head.appendChild(minBtn);

    var body = el('div', 'body');
    var sub = el('div', 'sub', '未开始');
    body.appendChild(sub);

    // target language
    var fLang = el('div', 'field');
    fLang.appendChild(el('label', null, '目标语言'));
    var selLang = el('select');
    LANGS.forEach(function (l) {
      var o = el('option', null, l.label);
      o.value = l.code;
      selLang.appendChild(o);
    });
    selLang.value = initial.target || 'en';
    fLang.appendChild(selLang);

    // voice mode
    var fVoice = el('div', 'field');
    fVoice.appendChild(el('label', null, '配音音色'));
    var selVoice = el('select');
    [['clone', '跟随原声（克隆）'], ['preset', '固定播音腔']].forEach(function (pair) {
      var o = el('option', null, pair[1]);
      o.value = pair[0];
      selVoice.appendChild(o);
    });
    selVoice.value = initial.voice || 'clone';
    fVoice.appendChild(selVoice);

    // original volume
    var fOrig = el('div', 'field');
    fOrig.appendChild(el('label', null, '原声音量'));
    var wrapOrig = el('div', 'range');
    var rngOrig = el('input');
    rngOrig.type = 'range'; rngOrig.min = '0'; rngOrig.max = '100'; rngOrig.step = '1';
    rngOrig.value = String(Math.round((initial.orig == null ? 0.12 : initial.orig) * 100));
    var valOrig = el('span', 'val', rngOrig.value + '%');
    wrapOrig.appendChild(rngOrig); wrapOrig.appendChild(valOrig);
    fOrig.appendChild(wrapOrig);

    // dub volume
    var fTts = el('div', 'field');
    fTts.appendChild(el('label', null, '译音音量'));
    var wrapTts = el('div', 'range');
    var rngTts = el('input');
    rngTts.type = 'range'; rngTts.min = '0'; rngTts.max = '100'; rngTts.step = '1';
    rngTts.value = String(Math.round((initial.tts == null ? 1 : initial.tts) * 100));
    var valTts = el('span', 'val', rngTts.value + '%');
    wrapTts.appendChild(rngTts); wrapTts.appendChild(valTts);
    fTts.appendChild(wrapTts);

    // subtitles switch
    var fSub = el('div', 'field');
    fSub.appendChild(el('label', null, '双语字幕'));
    var sw = el('div', 'switch' + (initial.subs === false ? '' : ' on'));
    sw.appendChild(el('i'));
    fSub.appendChild(sw);

    // server
    var fServer = el('div', 'field');
    fServer.appendChild(el('label', null, '引擎地址'));
    var inServer = el('input');
    inServer.type = 'text';
    inServer.spellcheck = false;
    inServer.value = initial.server || 'ws://127.0.0.1:8765/ws';
    fServer.appendChild(inServer);

    var meta = el('div', 'meta');
    var runBtn = el('button', 'run', '开始同传');
    var hint = el('div', 'hint', '');
    hint.style.display = 'none';

    body.appendChild(fLang); body.appendChild(fVoice); body.appendChild(fOrig); body.appendChild(fTts);
    body.appendChild(fSub); body.appendChild(fServer); body.appendChild(meta); body.appendChild(runBtn);
    body.appendChild(hint);
    panel.appendChild(head); panel.appendChild(body);
    root.appendChild(panel);

    var toast = el('div', 'toast');
    root.appendChild(toast);
    var toastTimer = 0;

    var api = {
      host: host,
      shadow: root,
      running: false,
      config: function () {
        return {
          target: selLang.value,
          voice: selVoice.value,
          orig: Number(rngOrig.value) / 100,
          tts: Number(rngTts.value) / 100,
          subs: sw.classList.contains('on'),
          server: inServer.value.trim()
        };
      },
      toast: function (text, ms) {
        toast.textContent = text;
        toast.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toast.classList.remove('show'); }, ms || 4200);
      },
      setStatus: function (text, kind) {
        dot.className = 'dot' + (kind ? ' ' + kind : '');
        sub.className = 'sub' + (kind ? ' ' + kind : '');
        sub.textContent = text || '未开始';
      },
      setRunning: function (running) {
        api.running = !!running;
        runBtn.textContent = running ? '停止同传' : '开始同传';
        runBtn.classList.toggle('stop', !!running);
        selLang.disabled = !!running;
      },
      setStats: function (stats) {
        meta.textContent = '';
        if (!stats) return;
        [['asr', '识别'], ['mt', '翻译'], ['tts', '配音'], ['total', '合计']].forEach(function (pair) {
          var v = stats[pair[0]];
          if (v == null || !isFinite(v)) return;
          var chip = el('span', 'chip');
          chip.appendChild(document.createTextNode(pair[1] + ' '));
          var b = el('b', null, Math.round(v) + 'ms');
          chip.appendChild(b);
          meta.appendChild(chip);
        });
      },
      setDiag: function (text) {
        var line = meta.querySelector('.chip.diag');
        if (!line) {
          line = el('span', 'chip diag');
          meta.appendChild(line);
        }
        line.textContent = text;
        line.style.display = text ? '' : 'none';
      },
      setDelay: function (seconds) {
        var existing = meta.querySelector('.chip.delay');
        if (!existing) {
          existing = el('span', 'chip delay');
          meta.appendChild(existing);
        }
        existing.textContent = '延迟 ' + seconds.toFixed(1) + 's';
      },
      setHint: function (text) {
        if (!text) { hint.style.display = 'none'; return; }
        hint.style.display = 'block';
        hint.textContent = text;
      },
      flashError: function (text) {
        api.setStatus('出错了，看下面的提示', 'err');
        api.toast(text, 6000);
      }
    };

    // drag the panel around (B站 right column is busy, users want to move it)
    head.addEventListener('mousedown', function (ev) {
      if (ev.target === minBtn) return;
      var rect = host.getBoundingClientRect();
      var ox = ev.clientX - rect.left;
      var oy = ev.clientY - rect.top;
      host.style.left = rect.left + 'px';
      host.style.top = rect.top + 'px';
      host.style.right = 'auto';
      function move(e) {
        var x = Math.max(4, Math.min(window.innerWidth - 90, e.clientX - ox));
        var y = Math.max(4, Math.min(window.innerHeight - 60, e.clientY - oy));
        host.style.left = x + 'px';
        host.style.top = y + 'px';
      }
      function up() {
        document.removeEventListener('mousemove', move, true);
        document.removeEventListener('mouseup', up, true);
      }
      document.addEventListener('mousemove', move, true);
      document.addEventListener('mouseup', up, true);
      ev.preventDefault();
    });

    // keep B站 player shortcuts (space / arrows) from firing while using the panel
    root.addEventListener('keydown', function (ev) { ev.stopPropagation(); });
    panel.addEventListener('mousedown', function (ev) { ev.stopPropagation(); });

    minBtn.addEventListener('click', function () {
      panel.classList.toggle('min');
      minBtn.textContent = panel.classList.contains('min') ? '+' : '–';
    });

    runBtn.addEventListener('click', function () {
      if (api.running) { opts.onStop && opts.onStop(); }
      else { opts.onStart && opts.onStart(api.config()); }
    });

    selLang.addEventListener('change', function () { opts.onConfig && opts.onConfig(api.config()); });
    selVoice.addEventListener('change', function () { opts.onConfig && opts.onConfig(api.config()); });
    rngOrig.addEventListener('input', function () {
      valOrig.textContent = rngOrig.value + '%';
      opts.onVolume && opts.onVolume(api.config());
    });
    rngTts.addEventListener('input', function () {
      valTts.textContent = rngTts.value + '%';
      opts.onVolume && opts.onVolume(api.config());
    });
    sw.addEventListener('click', function () {
      sw.classList.toggle('on');
      opts.onConfig && opts.onConfig(api.config());
    });
    inServer.addEventListener('change', function () { opts.onConfig && opts.onConfig(api.config()); });

    return api;
  }

  function createSubtitles() {
    var host = el('div');
    host.id = 'bsp-subs-host';
    host.style.cssText = 'position:fixed;left:0;right:0;bottom:76px;z-index:2147482999;pointer-events:none;';
    var root = host.attachShadow({ mode: 'open' });
    var style = el('style');
    style.textContent = [
      ':host { all: initial; }',
      '.wrap { display: flex; justify-content: center; padding: 0 8vw; }',
      '.box { max-width: 980px; text-align: center; padding: 10px 18px 12px; border-radius: 12px;',
      '  background: rgba(10,10,12,.62); backdrop-filter: blur(6px); opacity: 0; transform: translateY(6px);',
      '  transition: opacity .18s ease, transform .18s ease; }',
      '.box.show { opacity: 1; transform: translateY(0); }',
      '.src { font-family: "PingFang SC","Microsoft YaHei",system-ui,sans-serif; font-size: 15px; line-height: 1.45;',
      '  color: rgba(255,255,255,.62); margin-bottom: 4px; text-shadow: 0 1px 2px rgba(0,0,0,.7); }',
      '.dst { font-family: "PingFang SC","Microsoft YaHei",system-ui,sans-serif; font-size: 23px; line-height: 1.4;',
      '  font-weight: 600; color: #fff; letter-spacing: .2px; text-shadow: 0 2px 6px rgba(0,0,0,.85); }',
      '.dst.only { font-size: 19px; font-weight: 500; }',
      '.tag { display: inline-block; font-size: 11px; font-weight: 600; color: #ffc2d1; margin-right: 6px;',
      '  vertical-align: 2px; }',
      '.box.off { opacity: 0; }'
    ].join('\n');
    root.appendChild(style);

    var wrap = el('div', 'wrap');
    var box = el('div', 'box');
    var srcEl = el('div', 'src');
    var dstEl = el('div', 'dst');
    box.appendChild(srcEl);
    box.appendChild(dstEl);
    wrap.appendChild(box);
    root.appendChild(wrap);

    var hideTimer = 0;
    var api = {
      host: host,
      show: function (src, dst, opts) {
        opts = opts || {};
        srcEl.textContent = src || '';
        srcEl.style.display = src ? 'block' : 'none';
        dstEl.textContent = dst || src || '';
        dstEl.className = 'dst' + (dst ? '' : ' only');
        box.classList.add('show');
      },
      hide: function (immediate) {
        if (immediate) { box.classList.remove('show'); return; }
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () { box.classList.remove('show'); }, 1200);
      },
      destroy: function () { host.remove(); }
    };
    return api;
  }

  global.BSP_UI = { LANGS: LANGS, createPanel: createPanel, createSubtitles: createSubtitles };
})(window);
