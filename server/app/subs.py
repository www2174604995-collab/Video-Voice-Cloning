"""Subtitle handling: parse SRT, split over-long cues for TTS."""
from __future__ import annotations

import re
from typing import Dict, List

def merge_short(cues: List[Dict], max_sec: float = 14.0, max_chars: int = 70,
                gap: float = 0.8) -> List[Dict]:
    """Glue neighbouring_subtitle cues into whole sentences.

    Subtitle lines are fragments ("接下来是腮红。"), and a TTS model reads a
    fragment flat. Merging 2-4 cues until ~12-14 s gives it a complete thought,
    which is the single biggest naturalness win for dubbing.
    """
    if not cues:
        return cues
    out: List[Dict] = []
    cur = dict(cues[0])
    for c in cues[1:]:
        dur = c["t1"] - cur["t0"]
        text = cur["text"] + c["text"]
        if (dur <= max_sec and len(text) <= max_chars
                and c["t0"] - cur["t1"] <= gap):
            cur["t1"] = c["t1"]
            cur["text"] = text
        else:
            out.append(cur)
            cur = dict(c)
    out.append(cur)
    return out


def prepare(path: str, max_sec: float = 14.0) -> List[Dict]:
    """Parse, merge fragments, then split anything still too long."""
    return split_long(merge_short(parse_srt(path), max_sec=max_sec), max_sec=8.0)
