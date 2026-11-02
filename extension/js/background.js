/* Service worker: owns lifecycle, tab capture grant, offscreen document and
 * message routing between the content script and the audio engine. */

const OFFSCREEN_URL = 'html/offscreen.html';
const state = {
  running: new Map(),   // tabId -> { startedAt }
  lastConfig: new Map(),
  creating: null,
};

async function hasOffscreen() {
  try {
    if (chrome.offscreen && chrome.offscreen.hasDocument) {
      return await chrome.offscreen.hasDocument();
    }
  } catch (e) { /* ignore */ }
  return false;
}

async function ensureOffscreen() {
  if (await hasOffscreen()) return;
  if (state.creating) return state.creating;
  state.creating = chrome.offscreen
    .createDocument({
      url: OFFSCREEN_URL,
      reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],
      justification: '捕获当前标签页声音，并把翻译后的配音混回扬声器。',
    })
    .catch((err) => {
      const msg = String(err && err.message || err);
      if (msg.indexOf('single offscreen') === -1 && msg.indexOf('Only a single') === -1) throw err;
    })
    .finally(() => { state.creating = null; });
  return state.creating;
}

async function closeOffscreen() {
  try {
    if (await hasOffscreen()) await chrome.offscreen.closeDocument();
  } catch (e) { /* ignore */ }
}

async function unmuteTab(tabId) {
  try { await chrome.tabs.update(tabId, { muted: false }); } catch (e) { /* ignore */ }
}

async function hardStop(tabId, reason) {
  const known = state.running.get(tabId);
  state.running.delete(tabId);
  await ensureOffscreen().catch(() => {});
  try {
    await chrome.runtime.sendMessage({ to: 'offscreen', type: 'stop' });
  } catch (e) { /* ignore */ }
  await unmuteTab(tabId);
  try {
    await chrome.tabs.sendMessage(tabId, { to: 'content', type: 'stopped', reason: reason || 'user' });
  } catch (e) { /* ignore */ }
  if (state.running.size === 0) {
    setTimeout(() => { if (state.running.size === 0) closeOffscreen(); }, 1500);
  }
  return known;
}

async function startForTab(tabId, config) {
  if (state.running.has(tabId)) {
    return { ok: true, already: true };
  }
  state.lastConfig.set(tabId, config || {});
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab) return { ok: false, code: 'no-tab', message: '找不到标签页' };
  if (tab.url && tab.url.indexOf('bilibili.com') === -1) {
    return { ok: false, code: 'not-bilibili', message: '当前页面不是 B 站' };
  }

  await ensureOffscreen();

  let streamId = null;
  try {
    streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
  } catch (err) {
    const msg = String((err && err.message) || err);
    return {
      ok: false,
      code: 'gesture',
      message: '浏览器要求先点一下插件图标授权抓取声音：' + msg,
    };
  }

  // Chrome stops routing a captured tab's audio to the speakers, so the engine
  // plays the very same stream back through its own gain stage. We deliberately
  // do NOT mute the tab: muting can also silence the captured stream.
  try {
    const res = await chrome.runtime.sendMessage({
      to: 'offscreen',
      type: 'start',
      tabId: tabId,
      streamId: streamId,
      config: config || {},
    });
    if (!res || res.ok === false) throw new Error((res && res.error) || 'engine refused to start');
  } catch (err) {
    await unmuteTab(tabId);
    return { ok: false, code: 'engine', message: String((err && err.message) || err) };
  }

  state.running.set(tabId, { startedAt: Date.now() });
  state.lastConfig.set(tabId, config || {});
  return { ok: true };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== 'object') return false;

  if (msg.to === 'bg') {
    (async () => {
      const tabId = msg.tabId || (sender.tab && sender.tab.id);
      try {
        if (msg.type === 'start') {
          sendResponse(await startForTab(tabId, msg.config));
        } else if (msg.type === 'stop') {
          await hardStop(tabId, 'user');
          sendResponse({ ok: true });
        } else if (msg.type === 'state') {
          sendResponse({ ok: true, running: state.running.has(tabId) });
        } else {
          sendResponse({ ok: false, code: 'unknown', message: 'unknown message' });
        }
      } catch (err) {
        sendResponse({ ok: false, code: 'error', message: String((err && err.message) || err) });
      }
    })();
    return true;
  }

  // relay from the offscreen engine to the page
  if (msg.to === 'bg-relay' && msg.tabId) {
    const payload = Object.assign({ to: 'content' }, msg.payload || {});
    chrome.tabs.sendMessage(msg.tabId, payload).catch(() => {});
    return false;
  }

  return false;
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab || !tab.id) return;
  if (state.running.has(tab.id)) {
    await hardStop(tab.id, 'toggle');
    return;
  }
  const cfg = state.lastConfig.get(tab.id) || {};
  const res = await startForTab(tab.id, cfg);
  if (!res.ok) {
    chrome.tabs.sendMessage(tab.id, { to: 'content', type: 'need-gesture', message: res.message }).catch(() => {});
  } else {
    chrome.tabs.sendMessage(tab.id, { to: 'content', type: 'started', via: 'action' }).catch(() => {});
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (state.running.has(tabId)) hardStop(tabId, 'tab-closed');
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === 'loading' && state.running.has(tabId)) {
    hardStop(tabId, 'navigated');
  }
});
