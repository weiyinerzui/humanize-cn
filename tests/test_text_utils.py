"""Tests for text_utils.py — Chinese text segmentation utilities."""

import pytest
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from text_utils import split_sentences, merge_sentences


def test_split_chinese_sentences():
    """Split Chinese text at sentence terminators."""
    text = "这是第一句。这是第二句！这是第三句？"
    result = split_sentences(text)
    assert len(result) == 3
    assert "第一句" in result[0]
    assert "第二句" in result[1]
    assert "第三句" in result[2]


def test_split_preserves_paragraphs():
    """Split should handle multi-paragraph text."""
    text = "段落1句A。段落1句B。\n\n段落2句A。"
    result = split_sentences(text)
    assert len(result) >= 3


def test_merge_roundtrip():
    """merge_sentences should reconstruct original text."""
    text = "句子1。句子2。句子3。"
    parts = split_sentences(text)
    merged = merge_sentences(parts)
    assert merged == text


def test_split_empty():
    """Empty input should return empty list."""
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_split_mixed_en_zh():
    """Mixed English/Chinese with different terminators."""
    text = "This is a test. 中文句子。Another one."
    result = split_sentences(text)
    assert len(result) >= 3


def test_merge_single_sentence():
    """Merge single sentence returns same content."""
    assert merge_sentences(["单个句子。"]) == "单个句子。"
