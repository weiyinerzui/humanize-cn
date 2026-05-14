#!/usr/bin/env python3
"""
test_detect.py - detect.py 单元测试
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from detect import detect, get_level, score_sentences

# ─── 测试文本 ───

# 高AI味：三段式 + 连续成果罗列 + 机械连接词
TEXT_HIGH = """随着人工智能技术的不断发展，本文旨在探讨数字治理在农村基层治理中的应用，具有重要的理论意义和实践价值。
首先，值得注意的是，通过深度学习赋能，系统能够实现精准识别。
其次，借助知识图谱技术驱动，通过构建风险全景视图实现动态管理，通过整合多源数据实现精准评估。
最后，综上所述，取得了显著成效，短期偿债能力增强，经营活动现金流同比增长12.3%，流动比率从1.15提升至1.28。
"""

# 朱雀高分段落（实测AIGC=0.95/0.9982）
TEXT_ZHUQUE_HIGH = """四川长虹多元化战略下的筹资风险在智能财务风险管理技术的应用中得到显著改善，2024年企业短期借款占比同比下降5.2%，长期债券融资比例提升，综合融资成本降至4.8%，减轻了偿债压力。
基于深度强化学习的现金流预测模型提高了资金使用效率，经营活动现金流同比增长12.3%，流动比率从1.15提升至1.28，短期偿债能力增强。
此外，借助知识图谱技术，企业识别并拓展了供应链金融、绿色债券等新型融资方式，2024年非银融资占比达18%，降低了对传统银行贷款的依赖。
"""

# 低AI味（朱雀实测AIGC<0.2）：含具体年份/转折词/不完美描述
TEXT_LOW = """四川长虹于1994年3月在上海证券交易所正式挂牌上市，股票代码为SH600839。
企业初期以军工雷达制造为主，1973年转型进入家电领域，推出首台黑白电视机，1997年成为全球最大彩电制造商之一。
然而，传统静态的财务风险管控模式已经难以应对企业多元化战略下动态多变的市场环境，反而会在某些情况下加剧风险累积。
新业务投资项目回报滞后，虽中科美菱超低温冰箱市占率60%，但康养机器人等新赛道尚未形成规模收入。
"""

# 学术AI味：AI学术套话
TEXT_ACADEMIC = """本文旨在深入探讨智能财务风险管理的实现路径，具有重要的理论意义和实践价值。
研究表明，知识图谱技术已被广泛应用于风险识别领域，发挥着重要作用。
综上所述，本研究取得了显著的成效，为相关领域的研究奠定了坚实的基础，提供了重要的参考价值。
毫无疑问，智能技术必将在未来发挥越来越重要的作用，具有广阔的应用前景。
"""

# ─── 测试用例 ───

class TestScoring:
    def test_high_text_scores_above_50(self):
        r = detect(TEXT_HIGH)
        assert r.final_score >= 50, f"高AI文本得分应>=50，实际={r.final_score}"

    def test_zhuque_high_detects_consecutive_results(self):
        r = detect(TEXT_ZHUQUE_HIGH)
        cats = [i['category'] for i in r.issues]
        assert 'ZQ_连续成果罗列' in cats, "应检测到连续成果罗列"
        assert 'ZQ_完美总结段' in cats, "应检测到完美总结段"

    def test_zhuque_high_scores_above_40(self):
        r = detect(TEXT_ZHUQUE_HIGH)
        assert r.final_score >= 40, f"朱雀高分段落内部评分应>=40，实际={r.final_score}"

    def test_low_text_scores_below_35(self):
        r = detect(TEXT_LOW)
        assert r.final_score < 35, f"低AI文本得分应<35，实际={r.final_score}"

    def test_academic_ai_detected(self):
        r = detect(TEXT_ACADEMIC)
        cats = [i['category'] for i in r.issues]
        # 应至少检测到机械连接词或三段式
        detected = {'机械连接词', '三段式套路', 'ZQ_完美总结段'}
        assert any(c in cats for c in detected), f"学术AI套话未被检测到，issues={cats}"

    def test_academic_scores_above_threshold(self):
        r = detect(TEXT_ACADEMIC)
        assert r.final_score >= 30, f"学术AI文本得分应>=30，实际={r.final_score}"


class TestLevelLabels:
    def test_level_low(self):
        assert get_level(10) == 'LOW'
        assert get_level(24) == 'LOW'

    def test_level_medium(self):
        assert get_level(25) == 'MEDIUM'
        assert get_level(49) == 'MEDIUM'

    def test_level_high(self):
        assert get_level(50) == 'HIGH'
        assert get_level(69) == 'HIGH'

    def test_level_very_high(self):
        assert get_level(70) == 'VERY HIGH'
        assert get_level(100) == 'VERY HIGH'


class TestDimensionScores:
    def test_three_part_detected(self):
        r = detect(TEXT_HIGH)
        assert '三段式套路' in r.dimension_scores

    def test_mechanical_connectors_detected(self):
        text = "综上所述，不难发现，与此同时，由此可见，换句话说。"
        r = detect(text)
        assert '机械连接词' in r.dimension_scores

    def test_zq_yishi_detected(self):
        text = "一是筹资风险，企业面临融资压力；二是投资风险，存在信息不对称；三是营运风险，现金流管理复杂。"
        r = detect(text)
        assert 'ZQ_一是二是三是' in r.dimension_scores

    def test_reducer_bonus_applied(self):
        # 含转折词和具体数字 -> reducer_bonus 应为负数
        text = TEXT_LOW
        r = detect(text)
        assert r.reducer_bonus <= 0, "低AI文本应有降权补偿"


class TestSentenceScoring:
    def test_returns_top_sentences(self):
        sents = score_sentences(TEXT_HIGH, top_n=3)
        assert len(sents) <= 3

    def test_highest_sentence_has_ai_patterns(self):
        sents = score_sentences(TEXT_HIGH, top_n=5)
        if sents:
            top_score, top_text, reasons = sents[0]
            assert top_score > 0
            assert len(reasons) > 0


class TestEdgeCases:
    def test_empty_text_handled(self):
        # 短文本不应崩溃
        r = detect("你好。")
        assert r.final_score >= 0

    def test_long_text_no_crash(self):
        long = TEXT_HIGH * 10
        r = detect(long)
        assert 0 <= r.final_score <= 100

    def test_json_output_structure(self):
        r = detect(TEXT_HIGH)
        # 检查关键字段存在
        assert hasattr(r, 'final_score')
        assert hasattr(r, 'issues')
        assert hasattr(r, 'dimension_scores')
        assert hasattr(r, 'stats')
        assert 'chars' in r.stats
        assert 'sentences' in r.stats
        assert 'burstiness' in r.stats


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
