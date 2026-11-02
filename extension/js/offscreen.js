/* Invisible audio engine.
 *  - captures the tab audio through tabCapture
 *  - downsamples to 16 kHz PCM16 and streams it to the local engine over WS
 *  - plays the translated voice back, ducked under an adjustable original bed
 */
'use strict';

const st = {
  running: false,
  tabId: null,
  stream: null,
  ctx: null,
  srcNode: null,
  worklet: null,
  gainOrig: null,
  gainTts: null,
  ws: null,
  seq: 0,
  retries: 0,
  paused: false,
  passthrough: false,
  tick: { t: 0, at: 0, paused: true, rate: 1 },
  cfg: {
    server: 'ws://127.0.0.1:8765/ws',
    target: 'en',
    voice: 'clone',
    presetVoice: '',
    orig: 0.12,
    tts: 1.0,
    delay: 3.0,
  },
  player: { next: 0, sources: new Set() },
  latencies: [],
  dropCount: 0,
  stats: { chunks: 0, played: 0, dropped: 0, lastPlayAt: 0 },
  diagTimer: 0,
};

function log() {
  const args = Array.prototype.slice.call(arguments);
  console.log.apply(console, ['[BiliSimul]'].concat(args));
}

function post(payload) {
  if (!st.tabId) return;
  try {
    chrome.runtime.sendMessage({ to: 'bg-relay', tabId: st.tabId, payload: payload }).catch(function () {});
  } catch (e) { /* ignore */ }
}

function normalizeUrl(raw) {
  let url = String(raw || '').trim();
  if (!url) url = '127.0.0.1:8765';
  if (url.indexOf('ws://') !== 0 && url.indexOf('wss://') !== 0) {
    url = (url.indexOf('http://') === 0 ? 'ws://' : 'ws://') + url.replace(/^https?:\/\//, '');
  }
  if (!/\/ws(\?|$)/.test(url)) url = url.replace(/\/+$/, '') + '/ws';
  return url;
}

/* ---------------- clock ---------------- */

function vidNow() {
  const tk = st.tick;
  if (!tk || !tk.at) return null;
  const age = performance.now() / 1000 - tk.at;
  if (age > 3.5) return null;
  if (tk.paused) return tk.t;
  return tk.t + age * (tk.rate || 1);
}

/* ---------------- capture ---------------- */

async function start(msg) {
  await stop(true);
  st.tabId = msg.tabId;
  st.cfg = Object.assign({}, st.cfg, msg.config || {});
  st.paused = false;
  st.passthrough = false;
  st.dropCount = 0;
  st.retries = 0;
  st.seq = 0;

  st.stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: 'tab',
        chromeMediaSourceId: msg.streamId,
      },
    },
    video: false,
  });

  st.ctx = new AudioContext({ latencyHint: 'interactive' });
  await st.ctx.audioWorklet.addModule(chrome.runtime.getURL('js/pcm-worklet.js'));

  st.srcNode = st.ctx.createMediaStreamSource(st.stream);
  st.gainOrig = st.ctx.createGain();
  st.gainTts = st.ctx.createGain();
  st.gainOrig.gain.value = clamp01(st.cfg.orig);
  st.gainTts.gain.value = clamp01(st.cfg.tts);
  st.gainOrig.connect(st.ctx.destination);
  st.gainTts.connect(st.ctx.destination);

  st.worklet = new AudioWorkletNode(st.ctx, 'bsp-capture', {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: { targetRate: 16000, chunkMs: 100 },
  });
  const sink = st.ctx.createGain();
  sink.gain.value = 0;
  st.srcNode.connect(st.worklet);
  st.worklet.connect(sink);
  sink.connect(st.ctx.destination);
  st.srcNode.connect(st.gainOrig);
  st.worklet.port.onmessage = onPcm;

  if (st.ctx.state !== 'running') {
    try { await st.ctx.resume(); } catch (e) { /* ignore */ }
  }
  st.running = true;
  st.stats = { chunks: 0, played: 0, dropped: 0, lastPlayAt: 0 };
  startDiag();
  connectWS();
  log('started, ctx rate', st.ctx.sampleRate);
  return { ok: true, sampleRate: st.ctx.sampleRate };
}

function clamp01(v) {
  const n = Number(v);
  if (!isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function onPcm(ev) {
  const data = ev.data || {};
  const pcm = data.pcm;
  if (!pcm || !pcm.byteLength) return;
  const ws = st.ws;
  if (!ws || ws.readyState !== 1) return;
  const samples = data.samples || pcm.length;
  const rate = data.rate || 16000;
  st.stats.chunks += 1;
  const t1 = vidNow();
  const t0 = t1 == null ? 0 : t1 - samples / rate;

  const head = new ArrayBuffer(24);
  const dv = new DataView(head);
  [66, 83, 65, 49].forEach(function (b, i) { dv.setUint8(i, b); });
  dv.setUint32(4, st.seq++, true);
  dv.setFloat64(8, t0, true);
  dv.setFloat64(16, t1, true);

  const frame = new Uint8Array(24 + pcm.byteLength);
  frame.set(new Uint8Array(head), 0);
  frame.set(new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength), 24);
  try { ws.send(frame.buffer); } catch (e) { /* ignore */ }
}

/* ---------------- websocket ---------------- */

function connectWS() {
  closeWS();
  const url = normalizeUrl(st.cfg.server);
  let ws;
  try {
    ws = new WebSocket(url);
  } catch (err) {
    post({ type: 'error', message: '无法连接翻译引擎：' + err });
    return;
  }
  ws.binaryType = 'arraybuffer';
  st.ws = ws;

  ws.onopen = function () {
    st.retries = 0;
    ws.send(JSON.stringify({
      type: 'hello',
      target_lang: st.cfg.target,
      source_lang: 'auto',
      voice: st.cfg.voice,
      preset_voice: st.cfg.presetVoice || '',
    }));
    post({ type: 'status', status: 'online', server: url });
  };

  ws.onmessage = function (ev) {
    if (typeof ev.data === 'string') {
      let payload;
      try { payload = JSON.parse(ev.data); } catch (e) { return; }
      handleJson(payload);
    } else if (ev.data instanceof ArrayBuffer) {
      handleAudio(ev.data);
    }
  };

  ws.onerror = function () {
    post({ type: 'status', status: 'error' });
  };

  ws.onclose = function () {
    post({ type: 'status', status: 'offline' });
    if (!st.running) return;
    if (st.retries < 5) {
      const wait = 500 * Math.pow(1.6, st.retries);
      st.retries += 1;
      setTimeout(function () { if (st.running) connectWS(); }, wait);
    } else {
      post({ type: 'error', message: '与翻译引擎断开了，请确认服务端还在运行。' });
      st.running = false;
    }
  };
}

function closeWS() {
  if (st.ws) {
    try { st.ws.onclose = null; st.ws.close(); } catch (e) { /* ignore */ }
    st.ws = null;
  }
}

function handleJson(payload) {
  if (payload.type === 'stat') {
    const total = Number(payload.total);
    if (isFinite(total) && total > 0) {
      st.latencies.push(total);
      if (st.latencies.length > 12) st.latencies.shift();
      const sorted = st.latencies.slice().sort(function (a, b) { return a - b; });
      const median = sorted[Math.floor(sorted.length / 2)];
      // slow engines (XTTS on CPU) need a much larger budget than 6 s, otherwise
      // every segment arrives "too late" and gets dropped -> total silence
      const delay = Math.max(1.8, Math.min(14.0, median / 1000 + 0.9));
      st.cfg.delay = delay;
      payload.delay = Math.round(delay * 100) / 100;
    }
  }
  if (payload.type === 'passthrough') {
    st.passthrough = !!payload.on;
    applyVolumes();
    if (st.passthrough) flushPlayer();
  }
  post(payload);
}

/* ---------------- playback ---------------- */

function handleAudio(buffer) {
  if (buffer.byteLength < 28) return;
  const dv = new DataView(buffer);
  if (dv.getUint8(0) !== 66) return; // 'B'
  const id = dv.getUint32(4, true);
  const t0 = dv.getFloat64(8, true);
  const t1 = dv.getFloat64(16, true);
  const sr = dv.getFloat32(24, true);
  const pcm = new Float32Array(buffer, 28);

  const ctx = st.ctx;
  if (!ctx || !pcm.length) return;
  let audioBuf;
  try {
    audioBuf = ctx.createBuffer(1, pcm.length, Math.round(sr) || 24000);
    audioBuf.copyToChannel(pcm, 0);
  } catch (err) {
    log('buffer error', err);
    return;
  }
  schedule({ id: id, t0: t0, t1: t1, buf: audioBuf });
}

function schedule(item) {
  const ctx = st.ctx;
  const now = ctx.currentTime;
  const vn = vidNow();
  const rate = (st.tick && st.tick.rate) || 1;
  let lead = 0.05;
  let speed = 1;

  if (vn != null && item.t0 > 0) {
    lead = (item.t0 + st.cfg.delay - vn) / rate;
    if (lead < -0.25) {
      const late = -lead;
      if (late > 14.0) {
        st.dropCount += 1;
        st.stats.dropped += 1;
        post({ type: 'drop', late: Math.round(late * 100) / 100 });
        return;
      }
      // play it anyway: a late dub beats no dub
      speed = Math.min(1.15, 1 + (late / Math.max(1.0, item.buf.duration)) * 0.6);
      lead = 0;
    }
  }

  const startAt = Math.max(now + Math.max(0.03, lead), st.player.next - 0.03);
  const duration = item.buf.duration / speed;

  const src = ctx.createBufferSource();
  src.buffer = item.buf;
  src.playbackRate.value = speed;
  const gain = ctx.createGain();
  gain.gain.value = clamp01(st.cfg.tts);
  src.connect(gain);
  gain.connect(st.gainTts);
  src.onended = function () {
    st.player.sources.delete(src);
    try { src.disconnect(); gain.disconnect(); } catch (e) { /* ignore */ }
  };
  try {
    src.start(startAt);
  } catch (err) {
    log('start failed', err);
    return;
  }
  st.player.sources.add(src);
  st.player.next = startAt + duration;
  st.stats.played += 1;
  st.stats.lastPlayAt = ctx.currentTime;
}

function flushPlayer() {
  st.player.sources.forEach(function (src) {
    try { src.stop(); } catch (e) { /* ignore */ }
  });
  st.player.sources.clear();
  if (st.ctx) st.player.next = st.ctx.currentTime;
}

function startDiag() {
  if (st.diagTimer) clearInterval(st.diagTimer);
  st.diagTimer = setInterval(function () {
    if (!st.running) return;
    var ctxState = st.ctx ? st.ctx.state : 'none';
    post({
      type: 'diag',
      ctx: ctxState,
      chunks: st.stats.chunks,
      played: st.stats.played,
      dropped: st.stats.dropped,
      delay: Math.round(st.cfg.delay * 10) / 10,
      ws: st.ws && st.ws.readyState === 1 ? 'open' : 'closed',
    });
    st.stats.chunks = 0;
    st.stats.played = 0;
  }, 3000);
}

/* ---------------- control ---------------- */

function applyVolumes() {
  if (st.gainOrig) st.gainOrig.gain.value = st.passthrough ? 1.0 : clamp01(st.cfg.orig);
  if (st.gainTts) st.gainTts.gain.value = clamp01(st.cfg.tts);
}

async function stop(fromStart) {
  st.running = false;
  if (st.diagTimer) { clearInterval(st.diagTimer); st.diagTimer = 0; }
  closeWS();
  flushPlayer();
  if (st.worklet) {
    try { st.worklet.port.onmessage = null; st.worklet.disconnect(); } catch (e) { /* ignore */ }
    st.worklet = null;
  }
  if (st.stream) {
    try { st.stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) { /* ignore */ }
    st.stream = null;
  }
  if (st.ctx) {
    try { await st.ctx.close(); } catch (e) { /* ignore */ }
    st.ctx = null;
  }
  st.gainOrig = null;
  st.gainTts = null;
  st.srcNode = null;
  if (!fromStart) {
    st.tabId = null;
    post({ type: 'status', status: 'stopped' });
  }
}

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || msg.to !== 'offscreen') return false;
  (async function () {
    try {
      if (msg.type === 'start') {
        sendResponse(await start(msg));
      } else if (msg.type === 'stop') {
        await stop(false);
        sendResponse({ ok: true });
      } else if (msg.type === 'tick') {
        st.tabId = st.tabId || msg.tabId;
        const wasPaused = st.paused;
        st.tick = {
          t: Number(msg.t) || 0,
          at: performance.now() / 1000,
          paused: !!msg.paused,
          rate: Number(msg.rate) || 1,
        };
        st.paused = !!msg.paused;
        if (st.ctx && wasPaused !== st.paused) {
          if (st.paused) {
            flushPlayer();
            st.ctx.suspend().catch(function () {});
          } else {
            st.ctx.resume().catch(function () {});
          }
        }
        sendResponse({ ok: true });
      } else if (msg.type === 'resync') {
        flushPlayer();
        st.tick.at = 0;
        sendResponse({ ok: true });
      } else if (msg.type === 'volumes') {
        if (msg.orig != null) st.cfg.orig = msg.orig;
        if (msg.tts != null) st.cfg.tts = msg.tts;
        applyVolumes();
        sendResponse({ ok: true });
      } else if (msg.type === 'config') {
        if (msg.config) st.cfg = Object.assign(st.cfg, msg.config);
        applyVolumes();
        if (st.ws && st.ws.readyState === 1 && msg.config && (msg.config.target || msg.config.voice)) {
          st.ws.send(JSON.stringify({
            type: 'config',
            target_lang: st.cfg.target,
            voice: st.cfg.voice,
          }));
          flushPlayer();
        }
        sendResponse({ ok: true });
      } else {
        sendResponse({ ok: false, error: 'unknown' });
      }
    } catch (err) {
      sendResponse({ ok: false, error: String((err && err.message) || err) });
    }
  })();
  return true;
});
