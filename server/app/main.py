from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, dubbing
from .backends import Backends, build as build_backends
from .config import LANGUAGE_LABELS, PROJECT_DIR, Config, as_dict, load as load_config
from .session import Session

log = logging.getLogger("bilisimul")

WEB_DIR = PROJECT_DIR / "web"


class Runtime:
    """Holds the (lazily loaded) models shared by every session."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.backends: Optional[Backends] = None
        self.lock = threading.Lock()
        self.warmup_notes: list = []
        self.warmup_error = ""
        self.started = time.time()
        self.sessions = 0

    def ensure(self) -> Backends:
        with self.lock:
            if self.backends is None:
                self.backends = build_backends(self.cfg)
            return self.backends

    def warmup(self) -> None:
        try:
            backends = self.ensure()
            self.warmup_notes = backends.warmup()
            log.info("warmup done: %s", "; ".join(self.warmup_notes))
        except Exception as exc:  # pragma: no cover
            self.warmup_error = str(exc)
            log.exception("warmup failed")

    def describe(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "version": __version__,
            "uptime": round(time.time() - self.started, 1),
            "sessions": self.sessions,
            "backends": self.backends.describe() if self.backends else None,
            "warmup": self.warmup_notes,
            "config": {
                "asr": self.cfg.asr,
                "asr_model": self.cfg.asr_model,
                "mt": self.cfg.mt,
                "tts": self.cfg.tts,
                "voice": self.cfg.voice,
                "target_lang": "any",
            },
            "languages": [{"code": k, "label": v} for k, v in LANGUAGE_LABELS.items()],
        }
        if self.warmup_error:
            info["warmup_error"] = self.warmup_error
        return info


def build_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="BiliSimul", version=__version__, docs_url="/docs")
    rt = Runtime(cfg)
    app.state.runtime = rt

    @app.on_event("startup")
    async def _startup() -> None:
        if cfg.warmup:
            threading.Thread(target=rt.warmup, name="warmup", daemon=True).start()
        else:
            rt.ensure()

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(rt.describe())

    @app.get("/api/info")
    async def api_info() -> JSONResponse:
        return JSONResponse(rt.describe())

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        try:
            first = await asyncio.wait_for(ws.receive_text(), timeout=15.0)
            hello = json.loads(first)
        except Exception:
            await ws.close(code=4000)
            return
        if hello.get("type") not in (None, "hello", "start"):
            await ws.send_text(json.dumps({"type": "error", "message": "expected hello"}))
            await ws.close(code=4001)
            return

        try:
            backends = rt.ensure()
        except Exception as exc:  # pragma: no cover
            await ws.send_text(json.dumps({"type": "error", "message": f"backend init failed: {exc}"}))
            await ws.close(code=4100)
            return

        rt.sessions += 1
        session = Session(ws, cfg, backends, hello, runtime=rt)
        log.info("session %s start target=%s voice=%s", session.sid, session.target, session.voice_mode)
        try:
            await session.run()
        except WebSocketDisconnect:
            pass
        except Exception:  # pragma: no cover
            log.exception("session crashed")
        finally:
            rt.sessions = max(0, rt.sessions - 1)

    # ---- offline dubbing ("upload a video, get it re-voiced") ----
    uploads = PROJECT_DIR / "data" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    jobs: Dict[str, Dict[str, Any]] = {}
    jobs_lock = threading.Lock()

    def start_job(vpath, rpath, target: str, bg: float) -> str:
        jid = uuid.uuid4().hex[:12]
        out = uploads / jid / "dubbed.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        with jobs_lock:
            jobs[jid] = {"state": "queued", "stage": "queued", "done": 0, "total": 0,
                         "message": "排队中", "out": str(out), "name": "dubbed.mp4"}

        def report(stage: str, done: int, total: int, message: str) -> None:
            with jobs_lock:
                if jid in jobs:
                    jobs[jid].update(stage=stage, done=done, total=total,
                                     message=message, state="done" if stage == "done" else "running")

        def worker() -> None:
            try:
                dubbing.dub_video(str(vpath), str(rpath), str(out), target=target, bg=bg,
                                  cfg=cfg, backends=rt.ensure(), progress=report)
            except Exception as exc:  # pragma: no cover
                log.exception("dub %s failed", jid)
                with jobs_lock:
                    jobs[jid].update(state="error", message=str(exc)[:300])

        threading.Thread(target=worker, name=f"dub-{jid}", daemon=True).start()
        log.info("dub %s queued target=%s bg=%s", jid, target, bg)
        return jid

    @app.post("/api/dub")
    async def api_dub(
        video: UploadFile = File(...),
        ref: UploadFile = File(...),
        target: str = Form("same"),
        bg: float = Form(0.0),
    ) -> JSONResponse:
        folder = uploads / uuid.uuid4().hex[:12]
        folder.mkdir(parents=True, exist_ok=True)
        vname = "video" + (os.path.splitext(video.filename or ".mp4")[1] or ".mp4")
        rname = "ref" + (os.path.splitext(ref.filename or ".wav")[1] or ".wav")
        vpath, rpath = folder / vname, folder / rname
        with open(vpath, "wb") as fh:
            shutil.copyfileobj(video.file, fh)
        with open(rpath, "wb") as fh:
            shutil.copyfileobj(ref.file, fh)
        return JSONResponse({"id": start_job(vpath, rpath, target, bg)})

    @app.post("/api/dub_local")
    async def api_dub_local(payload: Dict[str, Any]) -> JSONResponse:
        """Reuse files already sitting on the server (upload them via JupyterLab: much faster)."""
        base = (PROJECT_DIR / "data" / "input").resolve()
        vpath = (base / str(payload.get("video", ""))).resolve()
        rpath = (base / str(payload.get("ref", ""))).resolve()
        for p in (vpath, rpath):
            if base not in p.parents or not p.is_file():
                return JSONResponse({"error": f"找不到 {p.name}"}, status_code=404)
        return JSONResponse({"id": start_job(vpath, rpath, str(payload.get("target", "same")),
                                             float(payload.get("bg", 0.0)))})

    @app.get("/api/dub_files")
    async def api_dub_files() -> JSONResponse:
        base = PROJECT_DIR / "data" / "input"
        if not base.is_dir():
            return JSONResponse({"files": []})
        names = sorted(p.name for p in base.iterdir() if p.is_file())
        return JSONResponse({"files": names})

    @app.get("/api/dub/{jid}")
    async def api_dub_status(jid: str) -> JSONResponse:
        with jobs_lock:
            job = jobs.get(jid)
            if not job:
                return JSONResponse({"error": "not found"}, status_code=404)
            payload = {k: v for k, v in job.items() if k != "out"}
        return JSONResponse(payload)

    @app.get("/api/dub/{jid}/file")
    async def api_dub_file(jid: str) -> FileResponse:
        with jobs_lock:
            job = jobs.get(jid)
            path = job.get("out") if job else None
        if not path or not os.path.isfile(path):
            return JSONResponse({"error": "not ready"}, status_code=404)
        return FileResponse(path, media_type="video/mp4", filename="dubbed.mp4")

    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(str(WEB_DIR / "index.html"))

        @app.get("/dub")
        async def dub_page() -> FileResponse:
            return FileResponse(str(WEB_DIR / "dub.html"))

    return app


app = build_app(load_config())
