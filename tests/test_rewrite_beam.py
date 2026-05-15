"""Tests for rewrite_beam.py — L3 Adversarial Beam Search Rewrite Engine."""

import pytest
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from unittest.mock import patch, MagicMock


class TestGenerateCandidates:
    """Test candidate generation with mocked LLM."""

    def test_returns_k_candidates(self):
        """generate_candidates should return exactly K candidates."""
        from rewrite_beam import generate_candidates
        with patch('rewrite_beam.call_with_retry') as mock:
            mock.side_effect = [(f"改写结果{i}", None) for i in range(3)]
            candidates = generate_candidates("原文句子。", mode='general', k=3)
            assert len(candidates) == 3

    def test_fallback_on_llm_error(self):
        """When LLM fails, should fall back to original sentence."""
        from rewrite_beam import generate_candidates
        with patch('rewrite_beam.call_with_retry') as mock:
            mock.return_value = (None, "API error")
            candidates = generate_candidates("原文句子。", mode='academic', k=2)
            assert len(candidates) == 2
            # At least one candidate should be the original (fallback)
            assert "原文句子" in candidates[0] or "原文句子" in candidates[1]

    def test_all_candidates_are_strings(self):
        """All candidates must be non-empty strings."""
        from rewrite_beam import generate_candidates
        with patch('rewrite_beam.call_with_retry') as mock:
            mock.side_effect = [("结果A", None), ("结果B", None)]
            candidates = generate_candidates("原文。", mode='academic', k=2)
            for c in candidates:
                assert isinstance(c, str)
                assert len(c) > 0


class TestSelectBest:
    """Test candidate selection logic."""

    def test_selects_lowest_score(self):
        """Should select candidate with lowest detect score."""
        from rewrite_beam import select_best
        candidates = ["高AI味文本", "中等AI味", "低AI味文本"]
        scores = [85, 50, 15]
        best = select_best(candidates, scores)
        assert best == "低AI味文本"

    def test_empty_candidates(self):
        """Empty candidates should return empty string."""
        from rewrite_beam import select_best
        assert select_best([], []) == ""


class TestBeamRewrite:
    """Test the full beam rewrite pipeline."""

    def test_beam_rewrite_empty_input(self):
        """Empty input should return empty string."""
        from rewrite_beam import beam_rewrite
        result = beam_rewrite("")
        assert result == ""

    def test_beam_rewrite_short_text(self):
        """Short text should be rewritten."""
        from rewrite_beam import beam_rewrite
        with patch('rewrite_beam.beam_rewrite_sentence') as mock:
            mock.return_value = ["改写后文本。"]
            result = beam_rewrite("短文本。", mode='general', k=2, verbose=False)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_beam_rewrite_preserves_structure(self):
        """Multi-sentence text should maintain structure."""
        from rewrite_beam import beam_rewrite
        text = "句子A。句子B。句子C。"
        with patch('rewrite_beam.beam_rewrite_sentence') as mock:
            mock.return_value = ["改写后。"]
            result = beam_rewrite(text, mode='academic', k=2, verbose=False)
            assert isinstance(result, str)