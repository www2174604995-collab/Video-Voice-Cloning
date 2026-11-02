from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import httpx

from ..config import LANGUAGE_NAMES, Config


@dataclass
class MTResult:
    text: str
    ms: float = 0.0
    ok: bool = True
    engine: str = ""


SYSTEM_PROMPT = (
    "You are a professional simultaneous interpreter dubbing online video. "
    "Translate the user's subtitle line into {target}. "
    "Rules: output ONLY the translation; no quotes, no notes, no romanization, no language label. "
    "Keep it natural and speakable, roughly the same length as the source line. "
    "Keep proper nouns, brand and product names in their usual form. "
    "The line may be a fragment of speech; translate it as a fragment, never invent content."
)


def _clean(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^(译文|翻译|Translation)\s*[:：]\s*", "", text, flags=re.I)
    text = text.strip().strip('"').strip("'").strip()
    text = text.replace("\n", " ").strip()
    return text


class LLMTranslator:
    """Any OpenAI-compatible chat endpoint (DeepSeek, Moonshot, Qwen, Ollama, ...)."""

    name = "llm"
    supports_context = True

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.base = (cfg.mt_base_url or "").rstrip("/")
        if self.base and not self.base.endswith("/v1") and "openai" not in self.base and "ollama" not in self.base:
            pass  # keep whatever the user configured
        self.detail = f"{cfg.mt_model} @ {self.base}"
        self._client: Optional[httpx.Client] = None

    def warmup(self) -> str:
        if not self.cfg.mt_api_key:
            return "mt: llm without api key (falls back to google/passthrough)"
        return "mt: " + self.detail

    def _http(self) -> httpx.Client:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.cfg.mt_api_key:
                headers["Authorization"] = "Bearer " + self.cfg.mt_api_key
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.cfg.mt_timeout, connect=6.0),
                headers=headers,
            )
        return self._client

    def translate(
        self,
        text: str,
        src: str,
        tgt: str,
        context: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> MTResult:
        started = time.time()
        target_name = LANGUAGE_NAMES.get(tgt, tgt)
        messages: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT.format(target=target_name)}]
        if context:
            for s, d in context:
                messages.append({"role": "user", "content": s})
                messages.append({"role": "assistant", "content": d})
        messages.append({"role": "user", "content": text})

        url = self.base + "/chat/completions"
        payload = {
            "model": self.cfg.mt_model,
            "messages": messages,
            "temperature": self.cfg.mt_temperature,
            "max_tokens": 512,
            "stream": False,
        }
        resp = self._http().post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return MTResult(text=_clean(content), ms=(time.time() - started) * 1000.0, engine="llm")


class GoogleTranslator:
    """Keyless fallback using the public translate endpoint (best effort)."""

    name = "google"
    supports_context = False

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = "translate.googleapis.com (keyless)"
        self._client = httpx.Client(timeout=httpx.Timeout(5.0, connect=4.0))

    def warmup(self) -> str:
        return "mt: " + self.detail

    def translate(
        self,
        text: str,
        src: str,
        tgt: str,
        context: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> MTResult:
        started = time.time()
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN" if tgt == "zh" else tgt,
            "dt": "t",
            "q": text,
        }
        resp = self._client.get("https://translate.googleapis.com/translate_a/single", params=params)
        resp.raise_for_status()
        data = resp.json()
        pieces = [chunk[0] for chunk in (data[0] or []) if chunk and chunk[0]]
        return MTResult(text=_clean("".join(pieces)), ms=(time.time() - started) * 1000.0, engine="google")


class MyMemoryTranslator:
    """Keyless community API (5k chars/day anonymous). Works where Google is blocked."""

    name = "mymemory"
    supports_context = False

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.detail = "mymemory (keyless, ~5k chars/day)"
        self._client = httpx.Client(timeout=httpx.Timeout(9.0, connect=5.0))

    def warmup(self) -> str:
        return "mt: " + self.detail

    def translate(
        self,
        text: str,
        src: str,
        tgt: str,
        context: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> MTResult:
        started = time.time()
        sl = (src or "en").lower().split("-")[0] or "en"
        if sl in ("auto", ""):
            sl = "en"
        tl = "zh-CN" if tgt == "zh" else tgt
        resp = self._client.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:480], "langpair": sl + "|" + tl},
        )
        resp.raise_for_status()
        data = resp.json()
        out = (data.get("responseData") or {}).get("translatedText") or ""
        if not out or "MYMEMORY WARNING" in out.upper() or "QUOTA" in out.upper():
            raise RuntimeError("mymemory quota or refusal")
        return MTResult(text=_clean(out), ms=(time.time() - started) * 1000.0, engine="mymemory")


class PassthroughTranslator:
    name = "passthrough"
    supports_context = False
    detail = "no translation"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def warmup(self) -> str:
        return "mt: passthrough"

    def translate(self, text, src, tgt, context=None) -> MTResult:
        return MTResult(text=text, ms=0.0, ok=False, engine="passthrough")


class MockTranslator:
    name = "mock"
    supports_context = True
    detail = "mock"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def warmup(self) -> str:
        return "mt: mock"

    def translate(self, text, src, tgt, context=None) -> MTResult:
        time.sleep(0.02)
        return MTResult(text="[" + tgt + "] " + text, ms=20.0, engine="mock")


class ChainMT:
    """Try engines in order, with a circuit breaker so a dead endpoint costs
    one timeout, not one per sentence for the rest of the video."""

    name = "chain"
    supports_context = True

    def __init__(self, engines: Sequence[object], labels: Sequence[str]) -> None:
        self.engines = list(engines)
        self.labels = list(labels)
        self.detail = " -> ".join(self.labels)
        self.name = self.labels[0] if self.labels else "mt"
        self._fails = {}

    def warmup(self) -> str:
        return "mt: " + self.detail

    def translate(self, text, src, tgt, context=None) -> MTResult:
        now = time.time()
        last_err = ""
        for engine, label in zip(self.engines, self.labels):
            state = self._fails.get(label)
            if state and state[1] > now:
                continue
            try:
                res = engine.translate(text, src, tgt, context)  # type: ignore[attr-defined]
                if res and res.text:
                    self._fails.pop(label, None)
                    res.engine = label
                    return res
            except Exception as exc:  # pragma: no cover - network dependent
                count = (state[0] if state else 0) + 1
                cooldown = 600.0 if count >= 2 else 0.0
                self._fails[label] = (count, now + cooldown)
                last_err = f"{label}: {exc}"
                continue
        return MTResult(text=text, ms=0.0, ok=False, engine="passthrough:" + last_err[:120])


def build_mt(cfg: Config):
    kind = (cfg.mt or "llm").lower()
    if kind in ("mock", "fake"):
        return MockTranslator(cfg)
    if kind in ("passthrough", "none", "off"):
        return PassthroughTranslator(cfg)
    if kind in ("google", "gtrans"):
        return ChainMT(
            [GoogleTranslator(cfg), MyMemoryTranslator(cfg), PassthroughTranslator(cfg)],
            ["google", "mymemory", "passthrough"],
        )
    if kind in ("mymemory", "mm"):
        return ChainMT([MyMemoryTranslator(cfg), PassthroughTranslator(cfg)], ["mymemory", "passthrough"])

    primary = LLMTranslator(cfg)
    local = "127.0.0.1" in (cfg.mt_base_url or "") or "localhost" in (cfg.mt_base_url or "")
    if not cfg.mt_api_key and not local:
        # no key: keyless chain that works behind the GFW as well
        return ChainMT(
            [MyMemoryTranslator(cfg), GoogleTranslator(cfg), PassthroughTranslator(cfg)],
            ["mymemory", "google", "passthrough"],
        )
    return ChainMT(
        [primary, MyMemoryTranslator(cfg), GoogleTranslator(cfg), PassthroughTranslator(cfg)],
        ["llm", "mymemory", "google", "passthrough"],
    )
