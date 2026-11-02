from __future__ import annotations

import os
import pathlib
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict

SERVER_DIR = pathlib.Path(__file__).resolve().parent.parent
PROJECT_DIR = SERVER_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml is a hard dependency, but keep import soft
    yaml = None


@dataclass
class Config:
    # ---- network ----
    host: str = "127.0.0.1"
    port: int = 8765
    model_dir: str = ""

    # ---- asr ----
    asr: str = "faster_whisper"          # faster_whisper | mock
    asr_model: str = "small"             # tiny/base/small/medium/large-v3
    asr_device: str = "auto"             # auto | cuda | cpu
    asr_compute_type: str = "auto"       # auto | float16 | int8_float16 | int8 | float32
    asr_beam_size: int = 1
    asr_language: str = "auto"           # auto or zh/en/ja/...
    hf_endpoint: str = "https://hf-mirror.com"   # set "" to use huggingface.co directly
    warmup: bool = True

    # ---- machine translation ----
    mt: str = "llm"                      # llm | google | mock | passthrough
    mt_base_url: str = "https://api.deepseek.com/v1"
    mt_model: str = "deepseek-chat"
    mt_api_key: str = ""
    mt_key_env: str = "DEEPSEEK_API_KEY"
    mt_temperature: float = 0.15
    mt_timeout: float = 15.0
    mt_context: int = 3                  # how many previous pairs to feed as context

    # ---- tts ----
    tts: str = "edge"                    # edge | sapi | xtts | indextts | voxcpm | cosyvoice | mock
    tts_device: str = "auto"              # auto | cuda | cpu（克隆引擎用哪块设备）
    voice: str = "clone"                 # clone | preset
    ref_audio: str = ""                 # 固定参考音（干净长音频）；留空=从视频里自动采
    preset_voice: str = ""               # empty -> pick by target language
    tts_speed: float = 1.06              # +6% keeps dubbing closer to source pace
    xtts_model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    xtts_dir: str = ""                # 本地 XTTS-v2 权重目录；留空则用 data/models/xtts_v2
    indextts_dir: str = ""            # 本地 IndexTTS-2 权重目录；留空则用 data/models/indextts2
    voxcpm_dir: str = ""              # 本地 VoxCPM-0.5B 权重目录；留空则用 data/models/voxcpm
    voxcpm_timesteps: int = 12         # 越大越细腻越慢（官方默认 10）
    voxcpm_cfg: float = 2.0            # 文本贴合强度：调高更清楚，调低更像参考音
    voxcpm_mode: str = "both"          # both=参考音+其文本（和官网一致）| ref=只用音色 | prompt=续写
    voxcpm_lora: str = ""              # 训练好的 LoRA 权重路径；留空=用原始模型
    voxcpm_lora_r: int = 32
    voxcpm_lora_alpha: int = 32
    voxcpm_normalize: bool = True      # 数字/符号文本归一化，能明显减少念错
    ref_trim: float = 15.0             # 参考音截取秒数；0 = 用完整参考音（和网站一致）
    voxcpm_retry: bool = True          # 生成异常（胡言乱语/长度离谱）时自动重生成
    dub_check: bool = True             # 离线配音逐句校验：语言/词/音色不对就重生成
    dub_candidates: int = 3            # 每句最多生成几次取最好（越大越慢越稳）
    repair_tts: str = ""               # 校验失败的句子用哪个引擎重做（如 indextts）
    dub_max_speedup: float = 1.0       # 每句最多压缩多少倍；1.0 = 完全不变速（推荐）
    sub_merge_sec: float = 14.0        # 相邻字幕合并到多少秒为一句（给模型完整句子）

    # ---- 两段式：先合成，再用 Seed-VC 把音色换成参考音 ----
    vc: bool = False                   # 打开后离线配音会调用 Seed-VC
    vc_dir: str = ""                   # seed-vc 仓库目录；留空用 ./seed-vc
    vc_python: str = ""                # seed-vc 的 venv python；留空用 ./seed-vc/.venv-vc/bin/python
    vc_steps: int = 25                 # 扩散步数，25 够用，30~50 更好但慢
    vc_cfg: float = 0.7                # 越大越贴参考音
    voxcpm_optimize: bool = True       # torch.compile：首次启动多等 2~4 分钟，之后每句 5~7 秒（关掉会慢到 40 秒以上）
    cosyvoice_dir: str = ""              # path to CosyVoice repo checkout

    # ---- segmentation ----
    vad_min_speech: float = 0.55         # seconds of speech before a segment can fire
    vad_max_segment: float = 6.0         # hard cut for long monologues
    vad_end_silence: float = 0.32        # silence that ends an utterance
    vad_energy: float = 0.0              # 0 = adaptive
    vad_frame_ms: int = 30

    # ---- voice cloning ----
    clone_ref_seconds: float = 7.0       # how much of the original speaker to enrol
    clone_min_segment: float = 0.8    # shortest utterance that can feed the voice profile

    # ---- misc ----
    log_level: str = "INFO"
    save_sessions: bool = False


def _coerce(cur: Any, raw: str) -> Any:
    if isinstance(cur, bool):
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(cur, int):
        return int(float(raw))
    if isinstance(cur, float):
        return float(raw)
    return raw


def load(path: str | os.PathLike | None = None) -> Config:
    """Load config.yaml (optional) then apply BS_* environment overrides."""
    cfg = Config()
    cfg.model_dir = str(DATA_DIR / "models")

    candidates = []
    if path:
        candidates.append(pathlib.Path(path))
    if os.environ.get("BILISIMUL_CONFIG"):
        candidates.append(pathlib.Path(os.environ["BILISIMUL_CONFIG"]))
    candidates.append(SERVER_DIR / "config.yaml")
    candidates.append(PROJECT_DIR / "config.yaml")

    for cand in candidates:
        try:
            if cand and cand.is_file():
                text = cand.read_text(encoding="utf-8")
                data = (yaml.safe_load(text) if yaml else None) or {}
                apply_dict(cfg, data)
                cfg._source = str(cand)  # type: ignore[attr-defined]
                break
        except Exception as exc:  # pragma: no cover
            print(f"[config] skip {cand}: {exc}")

    for f in fields(Config):
        env_key = "BS_" + f.name.upper()
        if env_key in os.environ:
            setattr(cfg, f.name, _coerce(getattr(cfg, f.name), os.environ[env_key]))

    if not cfg.mt_api_key and cfg.mt_key_env:
        cfg.mt_api_key = os.environ.get(cfg.mt_key_env, "")
    return cfg


def apply_dict(cfg: Config, data: Dict[str, Any]) -> None:
    known = {f.name for f in fields(Config)}
    for key, value in (data or {}).items():
        key = str(key)
        if key in known and value is not None:
            cur = getattr(cfg, key)
            if isinstance(cur, bool) and not isinstance(value, bool):
                value = str(value).lower() in ("1", "true", "yes", "on")
            elif isinstance(cur, int) and not isinstance(value, bool):
                value = int(value)
            elif isinstance(cur, float):
                value = float(value)
            setattr(cfg, key, value)


def as_dict(cfg: Config) -> Dict[str, Any]:
    return asdict(cfg)


LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "zh-Hant": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ru": "Russian",
    "pt": "Portuguese",
    "it": "Italian",
    "ar": "Arabic",
    "hi": "Hindi",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "tr": "Turkish",
    "nl": "Dutch",
    "pl": "Polish",
    "uk": "Ukrainian",
}

LANGUAGE_LABELS = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ru": "Русский",
    "pt": "Português",
    "it": "Italiano",
    "ar": "العربية",
    "hi": "हिन्दी",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
}
