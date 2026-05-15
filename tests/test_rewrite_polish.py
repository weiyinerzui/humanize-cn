"""Tests for rewrite_polish.py — L1 Rule-Based Polish Engine."""

import pytest
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rewrite_polish import polish, replace_mechanical_connectors


class TestReplaceConnectors:
    """Test mechanical connector replacement."""

    def test_removes_ai_tells(self):
        """Should replace AI-typical connectors."""
        text = "值得注意的是，人工智能发展迅速。"
        result = replace_mechanical_connectors(text)
        assert "值得注意的是" not in result

    def test_handles_multiple_connectors(self):
        """Multiple connectors in one text should be handled."""
        text = "值得注意的是，AI发展快。综上所述，需要关注风险。"
        result = replace_mechanical_connectors(text)
        assert "值得注意的是" not in result
        assert "综上所述" not in result

    def test_no_change_when_no_connectors(self):
        """Text without connectors should be unchanged."""
        text = "这是一个正常的句子。没有任何AI特征。"
        result = replace_mechanical_connectors(text)
        assert result == text


class TestPolish:
    """Test the main polish function."""

    def test_polish_returns_string(self):
        """polish should return a non-empty string."""
        result = polish("这是测试文本。", mode='academic')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_polish_empty_input(self):
        """Empty input should return empty string."""
        assert polish("") == ""
        assert polish("  ") == ""

    def test_polish_academic_preserves_terms(self):
        """Academic mode should preserve technical terms."""
        text = "量子计算推动了密码学研究的进步。"
        result = polish(text, mode='academic')
        assert "量子计算" in result
        assert "密码学" in result

    def test_polish_general_mode(self):
        """General mode should work without errors."""
        result = polish("测试文本内容。", mode='general')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_polish_with_ai_connectors(self):
        """Polish should clean AI connectors from text."""
        text = "值得注意的是，技术进步显著。与此同时，风险也在增加。"
        result = polish(text, mode='academic')
        # At least one connector should be replaced
        assert "值得注意的是" not in result or "与此同时" not in result