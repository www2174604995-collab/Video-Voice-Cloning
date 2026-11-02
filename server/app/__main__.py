from __future__ import annotations

import argparse
import logging
import os
import sys

import uvicorn

from .config import as_dict, load as load_config
from .main import build_app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bilisimul", description="BiliSimul realtime dubbing server")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--asr", default=None, help="faster_whisper | mock")
    parser.add_argument("--asr-model", default=None, help="tiny/base/small/medium/large-v3")
    parser.add_argument("--mt", default=None, help="llm | google | mock | passthrough")
    parser.add_argument("--tts", default=None, help="edge | sapi | xtts | indextts | voxcpm | cosyvoice | mock")
    parser.add_argument("--voice", default=None, help="clone | preset")
    parser.add_argument("--log-level", default=None, help="DEBUG | INFO | WARNING")
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    overrides = {
        "host": args.host,
        "port": args.port,
        "asr": args.asr,
        "asr_model": args.asr_model,
        "mt": args.mt,
        "tts": args.tts,
        "voice": args.voice,
        "log_level": args.log_level,
    }
    for key, value in overrides.items():
        if value:
            setattr(cfg, key, value)
    if args.no_warmup:
        cfg.warmup = False

    logging.basicConfig(
        level=getattr(logging, str(cfg.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    info = as_dict(cfg)
    print("=" * 62)
    print(" BiliSimul 服务端")
    print("=" * 62)
    print(" 监听      : http://{}:{}".format(cfg.host, cfg.port))
    print(" WebSocket : ws://{}:{}/ws".format(cfg.host, cfg.port))
    print(" 测试台    : http://{}:{}/".format(cfg.host, cfg.port))
    print(" 后端      : asr={}/{}  mt={}  tts={}/{}".format(
        cfg.asr, cfg.asr_model, cfg.mt, cfg.tts, cfg.voice))
    print("=" * 62)

    app = build_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level=str(cfg.log_level).lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
