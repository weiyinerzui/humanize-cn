#!/usr/bin/env python3
"""
test_integration.py - humanize.py 全流程集成测试

包含:
  - detect-only 模式
  - mock 改写（不调 LLM）
  - 完整 pipeline 结构验证
  - 文件输出验证
  - 多轮改写逻辑
"""
import sys
import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from humanize import pipeline, detect_only

# ─── 测试文本 ───

HIGH_AI_TEXT = """随着人工智能技术的不断发展，本文旨在探讨数字治理在农村基层治理中的应用，具有重要的理论意义和实践价值。
首先，值得注意的是，通过深度学习赋能，系统能够实现精准识别。
其次，借助知识图谱技术驱动，通过构建风险全景视图实现动态管理，通过整合多源数据实现精准评估。
最后，综上所述，取得了显著成效，短期偿债能力增强，经营活动现金流同比增长12.3%，流动比率从1.15提升至1.28。
"""

LOW_AI_TEXT = """四川长虹于1994年3月在上海证券交易所正式挂牌上市，股票代码为SH600839。
然而，传统静态的财务风险管控模式已经难以应对企业多元化战略下动态多变的市场环境，反而会在某些情况下加剧风险累积。
新业务投资项目回报滞后，虽中科美菱超低温冰箱市占率60%，但康养机器人等新赛道尚未形成规模收入。
"""

MOCK_REWRITTEN = """人工智能技术近年来快速发展，学界开始重新审视基层治理的数字化路径，本文由此切入。
深度学习在图像识别方面准确率较高，被引入系统设计，但效果仍有待实际场景验证。
多源数据整合为风险管理提供了技术条件，尽管数据质量参差不齐会影响结果。
从实测数据看，2024年经营现金流同比增长12.3%，这些变化与模型介入存在相关性，但因果关系尚需深入分析。
"""


class TestDetectOnly:
    def test_returns_detect_result(self, capsys):
        result = detect_only(HIGH_AI_TEXT)
        assert hasattr(result, 'final_score')
        assert result.final_score >= 0

    def test_prints_score(self, capsys):
        detect_only(HIGH_AI_TEXT)
        out = capsys.readouterr().out
        assert '/100' in out

    def test_high_ai_text_score_above_50(self):
        result = detect_only(HIGH_AI_TEXT)
        assert result.final_score >= 50

    def test_low_ai_text_score_below_35(self):
        result = detect_only(LOW_AI_TEXT)
        assert result.final_score < 35


class TestPipelineMocked:
    """用 mock 代替真实 LLM，验证 pipeline 结构正确性"""

    @patch('humanize.run_rewrite')
    def test_pipeline_returns_required_keys(self, mock_rw):
        mock_rw.return_value = {
            'rewritten': MOCK_REWRITTEN,
            'mode': 'academic',
            'intensity': 'aggressive',
            'model': 'mock-model',
            'error': None,
        }
        result = pipeline(HIGH_AI_TEXT, mode='academic')
        assert 'original' in result
        assert 'rewritten' in result
        assert 'detect_before' in result
        assert 'detect_after' in result
        assert 'report' in result

    @patch('humanize.run_rewrite')
    def test_pipeline_detect_before_is_result_object(self, mock_rw):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        result = pipeline(HIGH_AI_TEXT)
        assert hasattr(result['detect_before'], 'final_score')

    @patch('humanize.run_rewrite')
    def test_pipeline_detect_after_is_result_object(self, mock_rw):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        result = pipeline(HIGH_AI_TEXT)
        assert hasattr(result['detect_after'], 'final_score')

    @patch('humanize.run_rewrite')
    def test_pipeline_rewritten_text_propagated(self, mock_rw):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        result = pipeline(HIGH_AI_TEXT)
        assert result['rewritten'] == MOCK_REWRITTEN

    @patch('humanize.run_rewrite')
    def test_pipeline_auto_intensity_aggressive_for_high_score(self, mock_rw):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        pipeline(HIGH_AI_TEXT, intensity=None)
        call_kwargs = mock_rw.call_args
        # HIGH_AI_TEXT 得分 >= 60，应该传 aggressive
        # intensity 是关键字参数
        passed_intensity = call_kwargs[1].get('intensity') or call_kwargs[0][2]
        assert passed_intensity == 'aggressive'

    @patch('humanize.run_rewrite')
    def test_pipeline_error_in_rewrite_returns_original(self, mock_rw):
        mock_rw.return_value = {'rewritten': HIGH_AI_TEXT, 'model': 'mock', 'error': 'API 超时'}
        result = pipeline(HIGH_AI_TEXT)
        assert result['rewrite_result']['error'] == 'API 超时'
        # detect_after 应为 None
        assert result['detect_after'] is None

    @patch('humanize.run_rewrite')
    def test_pipeline_report_contains_text_report(self, mock_rw):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        result = pipeline(HIGH_AI_TEXT)
        assert 'text_report' in result['report']
        assert 'json_data' in result['report']

    @patch('humanize.run_rewrite')
    def test_pipeline_dry_run(self, mock_rw):
        mock_rw.return_value = {'rewritten': HIGH_AI_TEXT, 'model': 'mock', 'error': None, 'dry_run': True}
        result = pipeline(HIGH_AI_TEXT, dry_run=True)
        # dry_run 模式：rewrite 被调用但传 dry_run=True
        call_kwargs = mock_rw.call_args[1]
        assert call_kwargs.get('dry_run') is True


class TestPipelineFileOutput:
    """验证文件输出逻辑"""

    @patch('humanize.run_rewrite')
    def test_saves_two_files(self, mock_rw, tmp_path):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        input_file = tmp_path / 'test_input.txt'
        input_file.write_text(HIGH_AI_TEXT, encoding='utf-8')

        result = pipeline(HIGH_AI_TEXT, input_path=str(input_file))

        assert result['output_rewritten'] is not None
        assert result['output_report'] is not None
        assert os.path.exists(result['output_rewritten'])
        assert os.path.exists(result['output_report'])

    @patch('humanize.run_rewrite')
    def test_rewritten_file_content(self, mock_rw, tmp_path):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        input_file = tmp_path / 'paper.txt'
        input_file.write_text(HIGH_AI_TEXT, encoding='utf-8')

        result = pipeline(HIGH_AI_TEXT, input_path=str(input_file))
        with open(result['output_rewritten'], 'r', encoding='utf-8') as f:
            saved = f.read()
        assert saved == MOCK_REWRITTEN

    @patch('humanize.run_rewrite')
    def test_report_file_contains_key_info(self, mock_rw, tmp_path):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        input_file = tmp_path / 'paper.txt'
        input_file.write_text(HIGH_AI_TEXT, encoding='utf-8')

        result = pipeline(HIGH_AI_TEXT, input_path=str(input_file))
        with open(result['output_report'], 'r', encoding='utf-8') as f:
            report_text = f.read()
        assert 'AI 检测评分对比' in report_text
        assert '文本统计对比' in report_text

    @patch('humanize.run_rewrite')
    def test_custom_output_dir(self, mock_rw, tmp_path):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        input_file = tmp_path / 'paper.txt'
        input_file.write_text(HIGH_AI_TEXT, encoding='utf-8')
        out_dir = tmp_path / 'output'

        result = pipeline(HIGH_AI_TEXT, input_path=str(input_file),
                          output_dir=str(out_dir))
        assert out_dir.exists()
        assert result['output_rewritten'].startswith(str(out_dir))

    @patch('humanize.run_rewrite')
    def test_output_filenames_pattern(self, mock_rw, tmp_path):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        input_file = tmp_path / 'my_paper.txt'
        input_file.write_text(HIGH_AI_TEXT, encoding='utf-8')

        result = pipeline(HIGH_AI_TEXT, input_path=str(input_file))
        assert result['output_rewritten'].endswith('_rewritten.txt')
        assert result['output_report'].endswith('_report.txt')


class TestMultiRound:
    """多轮改写逻辑"""

    @patch('humanize.run_rewrite')
    def test_rounds_respected(self, mock_rw):
        # 每次都返回不同文本，模拟多轮
        # 第一轮改写后让评分仍然 >= 30（使用仍有AI味的文本），这样才不会提前停止
        HIGH_STILL = """首先，综上所述，通过深度学习赋能，系统能够实现精准识别，取得了显著成效。
其次，借助知识图谱，实现动态管理，经营活动现金流同比增长12.3%。
最后，值得注意的是，短期偿债能力增强，流动比率从1.15提升至1.28，能力增强。
"""
        mock_rw.side_effect = [
            {'rewritten': HIGH_STILL, 'model': 'mock', 'error': None},
            {'rewritten': '第二轮改写结果。这是第二轮的内容，更自然。', 'model': 'mock', 'error': None},
        ]
        result = pipeline(HIGH_AI_TEXT, rounds=2)
        # 应调用了 2 次（第一轮后评分仍高，不提前停止）
        assert mock_rw.call_count == 2
        assert '第二轮' in result['rewritten']

    @patch('humanize.run_rewrite')
    def test_rounds_capped_at_3(self, mock_rw):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        # rounds=5 应被限制到3
        result = pipeline(HIGH_AI_TEXT, rounds=5)
        # rounds 在 pipeline 内部有 min(max(1,r), 3) 限制
        assert mock_rw.call_count <= 3


class TestEdgeCases:
    @patch('humanize.run_rewrite')
    def test_empty_text_no_crash(self, mock_rw):
        mock_rw.return_value = {'rewritten': '', 'model': 'mock', 'error': None}
        # 极短文本
        result = pipeline('你好。', mode='general')
        assert result is not None

    @patch('humanize.run_rewrite')
    def test_general_mode_passed_through(self, mock_rw):
        mock_rw.return_value = {'rewritten': MOCK_REWRITTEN, 'model': 'mock', 'error': None}
        pipeline(HIGH_AI_TEXT, mode='general')
        call_kwargs = mock_rw.call_args[1]
        assert call_kwargs.get('mode') == 'general'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
