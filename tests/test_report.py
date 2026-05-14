#!/usr/bin/env python3
"""
test_report.py - report.py 单元测试
"""
import sys
import os
import json
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from report import (
    compute_stats, count_cliches, char_similarity, changed_ratio,
    sentence_diff, sample_changes, generate_report, format_text_report
)

# ─── 测试文本 ───

ORIG = """随着人工智能技术的不断发展，本文旨在探讨数字治理在农村基层治理中的应用，具有重要的理论意义和实践价值。
首先，值得注意的是，通过深度学习赋能，系统能够实现精准识别。
其次，借助知识图谱技术驱动，通过构建风险全景视图实现动态管理。
最后，综上所述，取得了显著成效，短期偿债能力增强，经营活动现金流同比增长12.3%。
"""

REWR = """人工智能技术近年来进展迅速，促使学界和实务界重新审视基层治理的数字化路径，本文由此切入。
深度学习在图像识别方面表现出较高准确率，这一特性被引入系统设计，但具体效果仍有待实际场景验证。
知识图谱与多源数据的整合为风险动态管理提供了技术条件，尽管数据质量参差不齐会影响最终结果。
从实测数据看，2024年经营现金流同比增长12.3%，流动比率小幅改善——这些变化与模型介入存在一定相关性，但因果关系尚需深入分析。
"""

# 完全相同的改写（用于相似度测试）
IDENTICAL = ORIG

# 极度不同（用于测试低相似度场景）
TOTALLY_DIFF = "苹果树上的小鸟唱着歌，河边的孩子们在玩耍，这是一个宁静的午后。"


class TestStats:
    def test_compute_stats_keys(self):
        stats = compute_stats(ORIG)
        assert 'chars' in stats
        assert 'sentences' in stats
        assert 'avg_sent_len' in stats
        assert 'burstiness' in stats
        assert 'cliche_count' in stats

    def test_cliche_count_high_in_orig(self):
        count = count_cliches(ORIG)
        assert count >= 3, f'原文套话数应>=3，实际={count}'

    def test_cliche_count_lower_in_rewr(self):
        orig_count = count_cliches(ORIG)
        rewr_count = count_cliches(REWR)
        assert rewr_count <= orig_count, \
            f'改写后套话数({rewr_count})不应高于原文({orig_count})'

    def test_burstiness_non_negative(self):
        stats = compute_stats(ORIG)
        assert stats['burstiness'] >= 0

    def test_chars_count_correct(self):
        stats = compute_stats('你好世界。Hello World.')
        # 4个中文字符
        assert stats['chars'] == 4


class TestSimilarity:
    def test_identical_similarity_is_one(self):
        s = char_similarity(ORIG, IDENTICAL)
        assert s == 1.0

    def test_different_text_similarity_low(self):
        s = char_similarity(ORIG, TOTALLY_DIFF)
        assert s < 0.5

    def test_changed_ratio_identical_is_zero(self):
        r = changed_ratio(ORIG, IDENTICAL)
        assert r == 0.0

    def test_changed_ratio_different_is_high(self):
        r = changed_ratio(ORIG, TOTALLY_DIFF)
        assert r > 0.5

    def test_partial_change_ratio_between_0_and_1(self):
        r = changed_ratio(ORIG, REWR)
        assert 0.0 < r < 1.0, f'改动率应在0-1之间，实际={r}'


class TestSentenceDiff:
    def test_identical_texts_all_unchanged(self):
        unch, chng, rmvd = sentence_diff(ORIG, IDENTICAL)
        assert chng == 0
        assert rmvd == 0

    def test_different_texts_have_changes(self):
        unch, chng, rmvd = sentence_diff(ORIG, TOTALLY_DIFF)
        total_new = chng
        assert total_new > 0

    def test_partial_rewrite_has_both(self):
        unch, chng, rmvd = sentence_diff(ORIG, REWR)
        # 有些句子变了，有些可能保留
        assert chng + rmvd > 0


class TestSampleChanges:
    def test_returns_list(self):
        examples = sample_changes(ORIG, REWR, n=3)
        assert isinstance(examples, list)
        assert len(examples) <= 3

    def test_example_structure(self):
        examples = sample_changes(ORIG, REWR, n=2)
        for orig_s, rewr_s, sim in examples:
            assert isinstance(orig_s, str)
            assert isinstance(rewr_s, str)
            assert 0.0 <= sim <= 1.0

    def test_no_identical_pairs(self):
        # 示例不应包含完全相同的对
        examples = sample_changes(ORIG, REWR, n=5)
        for orig_s, rewr_s, sim in examples:
            assert sim < 0.95, f'相似度{sim}过高，这是未改写的句子'


class TestGenerateReport:
    def test_returns_dict_with_keys(self):
        r = generate_report(ORIG, REWR, mode='academic', intensity='conservative')
        assert 'text_report' in r
        assert 'json_data' in r

    def test_text_report_is_string(self):
        r = generate_report(ORIG, REWR)
        assert isinstance(r['text_report'], str)
        assert len(r['text_report']) > 100

    def test_text_report_contains_key_sections(self):
        r = generate_report(ORIG, REWR)
        report = r['text_report']
        assert 'AI 检测评分对比' in report
        assert '文本统计对比' in report
        assert '句子改动分析' in report

    def test_json_data_structure(self):
        r = generate_report(ORIG, REWR, mode='general', intensity='aggressive', model='test-model')
        d = r['json_data']
        assert d['meta']['mode'] == 'general'
        assert d['meta']['intensity'] == 'aggressive'
        assert d['meta']['model'] == 'test-model'
        assert 'stats' in d['original']
        assert 'detect' in d['original']
        assert 'stats' in d['rewritten']
        assert 'detect' in d['rewritten']
        assert 'char_change_ratio' in d['diff']
        assert 'examples' in d['diff']

    def test_score_delta_calculated(self):
        r = generate_report(ORIG, REWR)
        delta = r['json_data']['diff']['score_delta']
        # delta 可能是 None（如果 detect 失败），但如果有值应是数字
        if delta is not None:
            assert isinstance(delta, (int, float))

    def test_rewrite_error_in_report(self):
        r = generate_report(ORIG, ORIG, rewrite_error='API 超时')
        report = r['text_report']
        assert '错误' in report
        assert 'API 超时' in report

    def test_identical_texts_zero_change_ratio(self):
        r = generate_report(ORIG, IDENTICAL)
        ratio = r['json_data']['diff']['char_change_ratio']
        assert ratio == 0.0

    def test_title_in_report(self):
        r = generate_report(ORIG, REWR, title='test_paper.txt')
        assert 'test_paper.txt' in r['text_report']


class TestEdgeCases:
    def test_empty_original(self):
        # 不崩溃
        r = generate_report('', '改写内容。')
        assert r['text_report']

    def test_short_text(self):
        r = generate_report('你好。', '您好。')
        assert r['json_data']['diff']['char_change_ratio'] >= 0

    def test_long_text_no_crash(self):
        long_orig = ORIG * 10
        long_rewr = REWR * 10
        r = generate_report(long_orig, long_rewr)
        assert r['json_data']['diff']['char_change_ratio'] > 0

    def test_json_serializable(self):
        r = generate_report(ORIG, REWR)
        # 应可以序列化为 JSON
        s = json.dumps(r['json_data'], ensure_ascii=False)
        assert s


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
