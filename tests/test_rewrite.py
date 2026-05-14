#!/usr/bin/env python3
"""
test_rewrite.py - rewrite.py 单元测试

LLM 调用相关的测试分两类:
  - 无网络测试（mock）: 测试 prompt 构建、output 清理、强度决策逻辑
  - 真实 LLM 测试（live）: 标记 @pytest.mark.live，需要 CF_API_TOKEN
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from rewrite import (
    build_system_prompt, get_intensity, _clean_llm_output,
    load_prompt, rewrite, call_llm
)

# ─── 测试文本 ───

TEXT_ACADEMIC = """随着人工智能技术的不断发展，本文旨在探讨数字治理在农村基层治理中的应用，具有重要的理论意义和实践价值。
首先，值得注意的是，通过深度学习赋能，系统能够实现精准识别。
其次，借助知识图谱技术驱动，通过构建风险全景视图实现动态管理，通过整合多源数据实现精准评估。
最后，综上所述，取得了显著成效，短期偿债能力增强，经营活动现金流同比增长12.3%。
"""

TEXT_GENERAL = """随着互联网时代的到来，数字化转型已成为各企业发展的重要战略方向。
值得注意的是，越来越多的企业开始重视数据的价值。
综上所述，数字化转型不仅是趋势，更是必然选择。
"""


# ─── Prompt 构建测试（无 LLM）───

class TestPromptBuilding:
    def test_load_academic_prompt(self):
        p = load_prompt('academic')
        assert '改写目标' in p or '学术' in p or 'INTENSITY' in p

    def test_load_general_prompt(self):
        p = load_prompt('general')
        assert 'INTENSITY' in p

    def test_build_academic_conservative(self):
        prompt = build_system_prompt('academic', 'conservative')
        assert '保守改写' in prompt
        assert '20-30%' in prompt or 'top 3' in prompt

    def test_build_academic_aggressive(self):
        prompt = build_system_prompt('academic', 'aggressive')
        assert '激进改写' in prompt or '25%' in prompt

    def test_build_general_mode(self):
        prompt = build_system_prompt('general', 'conservative')
        assert prompt  # 不为空

    def test_top_sentences_injected(self):
        top_sents = [
            (15, '综上所述，取得了显著成效', ['综上所述']),
            (10, '首先，值得注意的是', ['值得注意的是']),
        ]
        prompt = build_system_prompt('academic', 'aggressive', top_sentences=top_sents)
        assert '综上所述' in prompt or '风险15分' in prompt or '风险' in prompt

    def test_no_top_sentences_fallback(self):
        prompt = build_system_prompt('academic', 'conservative', top_sentences=None)
        assert '无句子级评分' in prompt


# ─── 强度决策测试 ───

class TestIntensityDecision:
    def test_low_score_gives_conservative(self):
        assert get_intensity(30) == 'conservative'
        assert get_intensity(59) == 'conservative'

    def test_high_score_gives_aggressive(self):
        assert get_intensity(60) == 'aggressive'
        assert get_intensity(90) == 'aggressive'

    def test_boundary_score(self):
        assert get_intensity(60) == 'aggressive'
        assert get_intensity(59) == 'conservative'


# ─── 输出清理测试 ───

class TestCleanOutput:
    def test_remove_prefix_gaixi_ruxia(self):
        raw = '改写如下：\n\n这是正文。'
        assert _clean_llm_output(raw) == '这是正文。'

    def test_remove_prefix_yixia_shi(self):
        raw = '以下是改写后的文本：\n这是正文。'
        assert _clean_llm_output(raw) == '这是正文。'

    def test_remove_prefix_hao_de(self):
        raw = '好的，根据您的要求改写如下：\n内容。'
        assert _clean_llm_output(raw) == '内容。'

    def test_remove_trailing_separator(self):
        raw = '正文内容。\n---'
        assert '---' not in _clean_llm_output(raw)

    def test_clean_normal_text_unchanged(self):
        raw = '这是正常的改写内容，无前缀。'
        assert _clean_llm_output(raw) == raw

    def test_multiline_output_preserved(self):
        raw = '第一段。\n\n第二段内容。'
        cleaned = _clean_llm_output(raw)
        assert '第一段' in cleaned
        assert '第二段' in cleaned


# ─── Mock LLM 测试 ───

class TestRewriteMocked:
    @patch('rewrite.call_with_retry')
    def test_rewrite_academic_returns_text(self, mock_call):
        mock_call.return_value = ('改写后的学术文本内容。', None)
        result = rewrite(TEXT_ACADEMIC, mode='academic', intensity='conservative')
        assert result['error'] is None
        assert '改写后的学术文本内容' in result['rewritten']
        assert result['mode'] == 'academic'

    @patch('rewrite.call_with_retry')
    def test_rewrite_general_returns_text(self, mock_call):
        mock_call.return_value = ('改写后的通用文本。', None)
        result = rewrite(TEXT_GENERAL, mode='general', intensity='aggressive')
        assert result['error'] is None
        assert result['intensity'] == 'aggressive'

    @patch('rewrite.call_with_retry')
    def test_rewrite_error_returns_original(self, mock_call):
        mock_call.return_value = (None, 'API 连接超时')
        result = rewrite(TEXT_ACADEMIC)
        assert result['error'] == 'API 连接超时'
        assert result['rewritten'] == TEXT_ACADEMIC  # fallback 原文

    @patch('rewrite.call_with_retry')
    def test_auto_intensity_from_detect(self, mock_call):
        mock_call.return_value = ('改写结果。', None)
        # 构造 mock detect_result（评分70，应触发 aggressive）
        dr = MagicMock()
        dr.final_score = 70
        result = rewrite(TEXT_ACADEMIC, detect_result=dr)
        assert result['intensity'] == 'aggressive'

    @patch('rewrite.call_with_retry')
    def test_auto_intensity_conservative_when_low(self, mock_call):
        mock_call.return_value = ('改写结果。', None)
        dr = MagicMock()
        dr.final_score = 30
        result = rewrite(TEXT_ACADEMIC, detect_result=dr)
        assert result['intensity'] == 'conservative'

    def test_dry_run_no_api_call(self):
        # dry_run 不应调用 LLM，返回原文
        result = rewrite(TEXT_ACADEMIC, dry_run=True)
        assert result.get('dry_run') is True
        assert result['rewritten'] == TEXT_ACADEMIC

    @patch('rewrite.call_with_retry')
    def test_llm_prefix_stripped(self, mock_call):
        mock_call.return_value = ('改写如下：\n\n这是干净的正文。', None)
        result = rewrite(TEXT_ACADEMIC)
        assert '改写如下' not in result['rewritten']
        assert '这是干净的正文。' in result['rewritten']

    @patch('rewrite.call_with_retry')
    def test_result_dict_structure(self, mock_call):
        mock_call.return_value = ('结果文本。', None)
        result = rewrite(TEXT_ACADEMIC)
        assert 'rewritten' in result
        assert 'mode' in result
        assert 'intensity' in result
        assert 'model' in result
        assert 'error' in result


# ─── 真实 LLM 测试（需 CF_API_TOKEN）───

@pytest.mark.live
class TestRewriteLive:
    """
    标记 @pytest.mark.live，默认跳过。
    运行: pytest tests/test_rewrite.py -m live -v
    需要: CF_API_TOKEN 环境变量
    """

    def test_live_academic_rewrite(self):
        import os
        if not (os.environ.get('QN_API_KEY') or os.environ.get('QNAIGC_API_TOKEN')):
            pytest.skip('CF_API_TOKEN 未设置')
        result = rewrite(TEXT_ACADEMIC, mode='academic', intensity='conservative')
        err = result.get('error', '')
        if err and any(k in err for k in ['neurons', '4006', 'upgrade', '429', 'No route']):
            pytest.skip(f'CF API 暂不可用: {err[:80]}')
        assert result['error'] is None, f"LLM 返回错误: {result['error']}"
        assert len(result['rewritten']) > 50, '改写结果太短'
        original_clichés = ['综上所述', '值得注意的是', '首先']
        clichés_remain = [c for c in original_clichés if c in result['rewritten']]
        assert len(clichés_remain) < len(original_clichés), \
            f'AI套话未被改写: {clichés_remain}'

    def test_live_general_rewrite(self):
        import os
        if not (os.environ.get('QN_API_KEY') or os.environ.get('QNAIGC_API_TOKEN')):
            pytest.skip('CF_API_TOKEN 未设置')
        result = rewrite(TEXT_GENERAL, mode='general', intensity='aggressive')
        err = result.get('error', '')
        if err and any(k in err for k in ['neurons', '4006', 'upgrade', '429', 'No route']):
            pytest.skip(f'CF API 暂不可用: {err[:80]}')
        assert result['error'] is None
        assert len(result['rewritten']) > 50

    def test_live_api_returns_nonempty(self):
        import os
        if not (os.environ.get('QN_API_KEY') or os.environ.get('QNAIGC_API_TOKEN')):
            pytest.skip('QN_API_KEY / QNAIGC_API_TOKEN 未设置')
        text, err = call_llm('你是助手。', '用一句话回复：你好', timeout=30)
        if err and ('neurons' in err or '4006' in err or 'upgrade' in err or '429' in err or 'No route' in err):
            pytest.skip(f'API 暂不可用(配额/路由): {err[:80]}')
        assert err is None, f'API 错误: {err}'
        assert text and len(text) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'not live'])
