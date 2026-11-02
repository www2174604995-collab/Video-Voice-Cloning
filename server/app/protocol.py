from __future__ import annotations

import struct
from typing import Tuple

import numpy as np

from . import audio as A

CLIENT_MAGIC = b"BSA1"
SERVER_MAGIC = b"BSB1"

# client -> server audio frame: magic, seq, video t0, video t1, pcm16 mono 16k
CLIENT_HEADER = struct.Struct("<4sIdd")
# server -> client audio frame: magic, segment id, t0, t1, sample rate, f32 mono pcm
SERVER_HEADER = struct.Struct("<4sIddf")


def pack_client_frame(seq: int, t0: float, t1: float, pcm: np.ndarray) -> bytes:
    return CLIENT_HEADER.pack(CLIENT_MAGIC, int(seq), float(t0), float(t1)) + A.f32_to_pcm16(pcm)


def unpack_client_frame(data: bytes) -> Tuple[int, float, float, np.ndarray]:
    if len(data) < CLIENT_HEADER.size:
        raise ValueError("frame too short")
    magic, seq, t0, t1 = CLIENT_HEADER.unpack_from(data, 0)
    if magic != CLIENT_MAGIC:
        raise ValueError("bad magic")
    pcm = A.pcm16_to_f32(data[CLIENT_HEADER.size :])
    return int(seq), float(t0), float(t1), pcm


def pack_audio_frame(seg_id: int, t0: float, t1: float, sr: int, pcm: np.ndarray) -> bytes:
    body = np.asarray(pcm, dtype="<f4").tobytes()
    return SERVER_HEADER.pack(SERVER_MAGIC, int(seg_id), float(t0), float(t1), float(sr)) + body


def unpack_audio_frame(data: bytes) -> Tuple[int, float, float, int, np.ndarray]:
    if len(data) < SERVER_HEADER.size:
        raise ValueError("frame too short")
    magic, seg_id, t0, t1, sr = SERVER_HEADER.unpack_from(data, 0)
    if magic != SERVER_MAGIC:
        raise ValueError("bad magic")
    pcm = np.frombuffer(data[SERVER_HEADER.size :], dtype="<f4").astype(np.float32)
    return int(seg_id), float(t0), float(t1), int(sr), pcm
