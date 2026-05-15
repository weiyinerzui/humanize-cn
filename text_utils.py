#!/usr/bin/env python3
"""Text segmentation utilities for Chinese text beam search."""

import re

_SENT_SPLIT = re.compile(r'([。！？；!?;.\n]+)')


def split_sentences(text: str, min_len: int = 4) -> list[str]:
    """Split text into sentences, preserving terminators.

    Uses a hybrid approach: splits on sentence terminators but
    merges fragments shorter than min_len with neighbors.
    """
    if not text or not text.strip():
        return []

    raw = _SENT_SPLIT.split(text)
    sentences = []
    buf = ""
    for part in raw:
        if not part:
            continue
        buf += part
        if _SENT_SPLIT.match(part):
            sentences.append(buf)
            buf = ""
    if buf.strip():
        sentences.append(buf)

    # Merge fragments shorter than min_len into neighbors
    merged = []
    for s in sentences:
        if merged and len(s.strip()) < min_len:
            merged[-1] += s
        else:
            merged.append(s)

    return merged


def merge_sentences(sentences: list[str]) -> str:
    """Merge sentences back, preserving spacing."""
    return ''.join(sentences)
