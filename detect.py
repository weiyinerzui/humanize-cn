#!/usr/bin/env python3
"""
detect.py - 中文AI文本检测引擎 v1.0
整合通用规则(20+维度) + 朱雀专项规则(7维度)
输出: 0-100评分 + 句子级标注 + JSON

用法:
  python3 detect.py text.txt
  python3 detect.py text.txt -v          # 详细模式
  python3 detect.py text.txt -s          # 仅评分
  python3 detect.py text.txt -j          # JSON输出
  python3 detect.py text.txt --sentences 5  # 显示最可疑N句
  echo "文本" | python3 detect.py        # stdin
"""

import sys
import re
import json
import os
import argparse
from collections import defaultdict
from math import log2

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATTERNS_BASE_FILE = os.path.join(SCRIPT_DIR, 'patterns', 'patterns_base.json')
PATTERNS_ZHUQUE_FILE = os.path.join(SCRIPT_DIR, 'patterns', 'patterns_zhuque.json')

# ─── 加载配置 ───

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

BASE_CFG = load_json(PATTERNS_BASE_FILE)
ZQ_CFG = load_json(PATTERNS_ZHUQUE_FILE)

# ─── 通用检测模式（来自 patterns_base.json） ───

def _get(cfg, *keys, default=None):
    obj = cfg
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k, None)
        if obj is None:
            return default
    return obj

MECH_CONNECTORS = _get(BASE_CFG, 'critical_patterns', 'mechanical_connectors', 'phrases', default=[
    '值得注意的是','综上所述','不难发现','总而言之',
    '与此同时','在此基础上','由此可见','不仅如此',
    '换句话说','更重要的是','需要强调的是','不可否认',
    '显而易见','不言而喻','正如我们所知','归根结底',
])
# 从检测标记中排除改写注入词（避免改写后反而加分）
_REWRITE_INJECT_WORDS = {'在一定程度上', '总体而言', '相较而言'}
MECH_CONNECTORS = [w for w in MECH_CONNECTORS if w not in _REWRITE_INJECT_WORDS]

EMPTY_GRAND = _get(BASE_CFG, 'critical_patterns', 'empty_grand_words', 'phrases', default=[
    '赋能','闭环','智慧时代','数字化转型','生态',
    '顶层设计','协同增效','降本增效','深度融合',
    '创新驱动','全方位','多维度','系统性',
])

THREE_PART_REGEX = _get(BASE_CFG, 'critical_patterns', 'three_part_structure', 'regex', default=[
    r'首先[，,].*?其次[，,].*?最后',
    r'一方面[，,].*?另一方面',
    r'第一[，,].*?第二[，,].*?第三',
])

AI_HIGH_FREQ = _get(BASE_CFG, 'high_signal_patterns', 'ai_high_freq_words', 'phrases', default=[
    '助力','彰显','凸显','焕发','深度剖析',
    '加持','赛道','破圈','颠覆','底层逻辑',
    '抓手','触达','沉淀','复盘','迭代',
])

FILLER_PHRASES = _get(BASE_CFG, 'high_signal_patterns', 'filler_phrases', 'phrases', default=[
    '值得一提的是','需要指出的是','不得不说',
    '毫无疑问','众所周知','具体来说','换言之',
])

TEMPLATE_REGEX = _get(BASE_CFG, 'high_signal_patterns', 'template_sentences', 'regex', default=[
    r'随着.*?的(不断)?发展',
    r'在.*?的背景下',
    r'在当今.*?时代',
    r'作为.*?的重要(组成部分|环节|手段)',
    r'这不仅.*?更是',
    r'可以说[，,]',
    r'总的来说[，,]',
])

HEDGING_PHRASES = _get(BASE_CFG, 'medium_signal_patterns', 'hedging_language', 'phrases', default=[
    '或许','某种程度上','相对而言',
    '总体来说','一般来说','通常情况下',
])
HEDGING_PHRASES = [w for w in HEDGING_PHRASES if w not in _REWRITE_INJECT_WORDS]

EMOTIONAL_WORDS = _get(BASE_CFG, 'style_signals', 'emotional_words', default=[
    '愤怒','高兴','难过','失望','惊讶','担心',
    '开心','郁闷','焦虑','兴奋','害怕','感动',
])

PERSONAL_MARKERS = _get(BASE_CFG, 'style_signals', 'personal_markers', default=[
    '我认为','我觉得','笔者','在我看来','个人认为',
    '我的理解','据我所知','从我的角度',
])

# ─── 朱雀专项检测模式 ───

ZQ_CRIT = ZQ_CFG.get('zhuque_critical', {})
ZQ_HIGH = ZQ_CFG.get('zhuque_high', {})
ZQ_MED  = ZQ_CFG.get('zhuque_medium', {})
ZQ_RED  = ZQ_CFG.get('zhuque_reducers', {})

def _zq_phrases(section, key):
    return ZQ_CFG.get(section, {}).get(key, {}).get('phrases', [])

def _zq_regex(section, key):
    return ZQ_CFG.get(section, {}).get(key, {}).get('regex', [])

ZQ_PERFECT_SUMMARY_PHRASES = _zq_phrases('zhuque_critical', 'perfect_summary_block')
ZQ_FUNC_PHRASES = _zq_phrases('zhuque_high', 'function_description_templates')
ZQ_FUNC_REGEX   = _zq_regex('zhuque_high', 'function_description_templates')
ZQ_YISHI_REGEX  = _zq_regex('zhuque_high', 'three_part_yishi')
ZQ_DENSE_REGEX  = _zq_regex('zhuque_high', 'dense_logic_connectors')
ZQ_AI_VERBS     = _zq_phrases('zhuque_medium', 'zhuque_ai_verbs')
ZQ_CHAIN_REGEX  = _zq_regex('zhuque_medium', 'risk_transmission_chain')
ZQ_ADV_PHRASES  = _zq_phrases('zhuque_reducers', 'adversative_complex')

ZQ_CONSEC_RESULT_REGEX = _zq_regex('zhuque_critical', 'consecutive_result_sentences')
ZQ_CONSEC_THROUGH_REGEX = _zq_regex('zhuque_critical', 'consecutive_through_achieve')

# ─── 工具函数 ───

def split_sentences(text):
    parts = re.split(r'([。！？；\n])', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i].strip()
        if s:
            sentences.append(s + (parts[i+1] if i+1 < len(parts) else ''))
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append(parts[-1].strip())
    return [s for s in sentences if len(s) > 2]

def count_chinese(text):
    return len(re.findall(r'[\u4e00-\u9fff]', text))

def char_entropy(text):
    chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(chars) < 10:
        return 5.0
    bigrams = defaultdict(int)
    for i in range(len(chars) - 1):
        bigrams[chars[i] + chars[i+1]] += 1
    total = sum(bigrams.values())
    if total == 0:
        return 5.0
    entropy = sum(-(c/total)*log2(c/total) for c in bigrams.values() if c > 0)
    return round(entropy, 2)

def sentence_lengths(text):
    sents = split_sentences(text)
    return [count_chinese(s) for s in sents if count_chinese(s) > 0]

def burstiness(lengths):
    if len(lengths) < 3:
        return 0.0
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.0
    std = (sum((x - mean)**2 for x in lengths) / len(lengths)) ** 0.5
    return round(std / mean, 3)

def ngram_perplexity(text):
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from ngram_model import analyze_text
        result = analyze_text(text)
        return result.get('perplexity', None)
    except Exception:
        return None

# ─── 检测引擎 ───

class DetectionResult:
    def __init__(self):
        self.issues = []          # list of (category, severity, description, snippet)
        self.dimension_scores = {}
        self.reducer_bonus = 0
        self.raw_score = 0
        self.final_score = 0
        self.stats = {}

    def add(self, category, severity, description, snippet=''):
        self.issues.append({
            'category': category,
            'severity': severity,
            'description': description,
            'snippet': snippet[:80]
        })

    def add_dim(self, dim, score):
        self.dimension_scores[dim] = self.dimension_scores.get(dim, 0) + score

def detect(text):
    result = DetectionResult()
    sentences = split_sentences(text)
    lengths = sentence_lengths(text)
    n_chars = count_chinese(text)
    n_sents = len(sentences)

    # ── 统计基础 ──
    entropy = char_entropy(text)
    burst = burstiness(lengths)
    avg_len = sum(lengths)/len(lengths) if lengths else 0
    perp = ngram_perplexity(text)
    emotion_density = sum(1 for w in EMOTIONAL_WORDS if w in text) / max(n_sents, 1)
    personal_count = sum(1 for w in PERSONAL_MARKERS if w in text)

    result.stats = {
        'chars': n_chars,
        'sentences': n_sents,
        'avg_sent_len': round(avg_len, 1),
        'entropy': entropy,
        'burstiness': burst,
        'perplexity': perp,
        'emotion_density': round(emotion_density * 100, 2),
        'personal_markers': personal_count,
    }

    # ── 1. 三段式套路（通用）── weight 12
    for pat in THREE_PART_REGEX:
        for m in re.finditer(pat, text, re.DOTALL):
            result.add('三段式套路', 'critical', '首先/其次/最后 或 一方面/另一方面', m.group()[:60])
            result.add_dim('三段式套路', 12)

    # ── 2. 机械连接词（通用）── weight 8
    mc_count = sum(text.count(p) for p in MECH_CONNECTORS)
    if mc_count > 0:
        found = [p for p in MECH_CONNECTORS if p in text]
        result.add('机械连接词', 'high', f'出现 {mc_count} 处: {", ".join(found[:4])}')
        result.add_dim('机械连接词', min(mc_count * 4, 20))

    # ── 3. 空洞宏大词（通用）── weight 5
    grand_found = [p for p in EMPTY_GRAND if p in text]
    if grand_found:
        result.add('空洞宏大词', 'high', f'{", ".join(grand_found[:5])}')
        result.add_dim('空洞宏大词', min(len(grand_found) * 3, 12))

    # ── 4. AI高频词（通用）── weight 4
    hf_found = [p for p in AI_HIGH_FREQ if p in text]
    if hf_found:
        result.add('AI高频词', 'medium', f'{", ".join(hf_found[:6])}')
        result.add_dim('AI高频词', min(len(hf_found) * 3, 10))

    # ── 5. 填充废话（通用）── weight 4
    fill_found = [p for p in FILLER_PHRASES if p in text]
    if fill_found:
        result.add('填充废话', 'medium', f'{", ".join(fill_found[:4])}')
        result.add_dim('填充废话', min(len(fill_found) * 3, 10))

    # ── 6. 模板句式（通用）── weight 5
    for pat in TEMPLATE_REGEX:
        for m in re.finditer(pat, text):
            result.add('模板句式', 'medium', f'匹配: {pat}', m.group())
            result.add_dim('模板句式', 5)

    # ── 7. 统计特征：低burstiness ── weight 8
    if burst < 0.25 and n_sents >= 5:
        result.add('句长单调', 'high',
            f'爆发度={burst}（人类写作通常>0.4），平均句长={avg_len:.0f}字')
        result.add_dim('句长单调', int((0.5 - burst) * 30))

    # ── 8. 困惑度低（通用）── weight 6
    if perp is not None and 0 < perp < 500:
        result.add('困惑度异常低', 'high',
            f'困惑度={perp:.1f}（AI文本通常<500）')
        result.add_dim('困惑度低', min(int((500 - perp) / 50), 12))

    # ── 9. 情感平淡（通用）── weight 3
    if emotion_density < 0.01 and n_sents > 5:
        result.add('情感平淡', 'low', f'情感/个人表达密度{emotion_density*100:.2f}%，偏低')
        result.add_dim('情感平淡', 3)

    # ── 10. 过度犹豫语（通用）── weight 2
    hedge_count = sum(text.count(p) for p in HEDGING_PHRASES)
    if hedge_count > 5:
        result.add('过度犹豫语', 'low', f'出现 {hedge_count} 处')
        result.add_dim('过度犹豫语', 2)

    # ── 11. 学术套话（通用）── weight 8
    ACADEMIC_CLICHE = [
        '具有重要的理论意义', '具有重要意义', '理论意义和实践价值',
        '研究表明', '研究发现', '大量研究', '众多学者',
        '广泛应用于', '被广泛应用', '发挥着重要作用',
        '奠定了坚实的基础', '奠定坚实基础', '提供了重要参考',
        '具有广阔的应用前景', '具有重要参考价值', '提供参考价值',
        '毫无疑问', '不可否认', '显而易见', '不言而喻',
        '必将在未来', '越来越重要', '日益重要', '不可或缺',
        '取得了显著成效', '取得了重要进展', '填补了.*空白',
        '本研究.*创新', '创新之处在于',
    ]
    ac_found = [p for p in ACADEMIC_CLICHE if re.search(p, text)]
    if ac_found:
        result.add('学术套话', 'high',
                   f'出现 {len(ac_found)} 处学术腔模板: {", ".join(ac_found[:4])}')
        result.add_dim('学术套话', min(len(ac_found) * 5, 20))

    # ── 12. 结论段完美表述（通用）── weight 6
    CONCLUSION_CLICHE_REGEX = [
        r'综上所述.{0,30}(取得|实现|提升|改善|发现)',
        r'通过(本文|本研究).{0,20}(验证|证明|表明)',
        r'(为|对).{0,15}(提供|具有).{0,15}(参考|价值|意义)',
    ]
    for pat in CONCLUSION_CLICHE_REGEX:
        if re.search(pat, text, re.DOTALL):
            result.add('结论段套话', 'medium', f'结论段完美总结模板: {pat[:40]}')
            result.add_dim('结论段套话', 6)
            break

    # ════════════════════════════════════════
    # 朱雀专项维度（ZQ）
    # ════════════════════════════════════════

    # ── ZQ1. 连续成果罗列句（窗口分析，最高权重）── weight 18
    # 朱雀检测的是跨句子的"每句都是成效描述"模式，不能用单句正则
    RESULT_VERBS = [
        '得到显著','得到有效','减轻了','提升至','同比增长','同比下降',
        '降至','增强','提高了','流动比率','占比达','降低了',
        '取得了','有效改善','短期偿债','能力增强','比例提升',
        '同比提升','同比减少','成本降至','效率提升','增长了',
    ]
    zq1_count = 0
    result_sent_flags = [any(v in s for v in RESULT_VERBS) for s in sentences]
    for i in range(len(result_sent_flags) - 1):
        if result_sent_flags[i] and result_sent_flags[i+1]:
            snippet = (sentences[i][:40] + '…' + sentences[i+1][:30]) if len(sentences) > i+1 else sentences[i][:60]
            result.add('ZQ_连续成果罗列', 'critical',
                '连续多句"指标+改善动词+数字"高度均匀，朱雀AIGC值0.95触发器',
                snippet)
            zq1_count += 1
    if zq1_count:
        result.add_dim('ZQ_连续成果罗列', min(zq1_count * 14, 36))

    # ── ZQ2. 连续"通过X实现Y"模板（窗口分析，最高权重）── weight 18
    THROUGH_VERBS = ['通过', '借助']
    ACHIEVE_VERBS = ['实现', '提供', '构建', '形成', '生成', '完成', '支撑', '保障']
    through_flags = [
        any(s.startswith(v) or f'，{v}' in s for v in THROUGH_VERBS) and
        any(v in s for v in ACHIEVE_VERBS)
        for s in sentences
    ]
    zq2_count = 0
    for i in range(len(through_flags) - 1):
        if through_flags[i] and through_flags[i+1]:
            snippet = sentences[i][:50] if sentences else ''
            result.add('ZQ_通过实现模板', 'critical',
                '连续多句"通过手段+实现结果"模板，朱雀AIGC值0.99触发器',
                snippet)
            zq2_count += 1
    if zq2_count:
        result.add_dim('ZQ_通过实现模板', min(zq2_count * 14, 36))

    # ── ZQ3. 完美总结段（高权重）── weight 12
    zq3_found = [p for p in ZQ_PERFECT_SUMMARY_PHRASES if re.search(p, text)]
    if len(zq3_found) >= 2:
        result.add('ZQ_完美总结段', 'critical',
            f'集中出现多个成效表述（{len(zq3_found)}处），无局限说明: {", ".join(zq3_found[:3])}')
        result.add_dim('ZQ_完美总结段', min(len(zq3_found) * 6, 18))

    # ── ZQ4. 功能描述套话（高权重）── weight 10
    zq4_found = [p for p in ZQ_FUNC_PHRASES if p in text]
    zq4_regex = sum(1 for pat in ZQ_FUNC_REGEX if re.search(pat, text, re.DOTALL))
    if zq4_found or zq4_regex:
        result.add('ZQ_功能描述套话', 'high',
            f'系统功能高度模板化: {", ".join(zq4_found[:3])}')
        result.add_dim('ZQ_功能描述套话', min((len(zq4_found) + zq4_regex * 2) * 4, 16))

    # ── ZQ5. 一是二是三是（高权重）── weight 8
    for pat in ZQ_YISHI_REGEX:
        if re.search(pat, text, re.DOTALL):
            result.add('ZQ_一是二是三是', 'high', '一是/二是/三是三段式结构')
            result.add_dim('ZQ_一是二是三是', 8)
            break

    # ── ZQ6. 朱雀AI动词（中权重）── weight 5
    zq6_found = [p for p in ZQ_AI_VERBS if p in text]
    if zq6_found:
        result.add('ZQ_AI动词', 'medium',
            f'{", ".join(zq6_found[:6])}')
        result.add_dim('ZQ_AI动词', min(len(zq6_found) * 2, 10))

    # ── ZQ7. 传导链描述（中权重）── weight 6
    for pat in ZQ_CHAIN_REGEX:
        if re.search(pat, text):
            result.add('ZQ_传导链描述', 'medium', '箭头传导链模板句式')
            result.add_dim('ZQ_传导链描述', 6)
            break

    # ════════════════════════════════════════
    # 朱雀降权项（Reducers）
    # ════════════════════════════════════════

    # 转折词 / 不完美表达
    adv_count = sum(1 for p in ZQ_ADV_PHRASES if p in text)
    if adv_count >= 2:
        result.reducer_bonus -= min(adv_count * 2, 8)

    # 精确数字密度
    num_matches = re.findall(r'\d+\.\d+%|\d+(?:亿|万)元', text)
    if len(num_matches) >= 3:
        result.reducer_bonus -= min(len(num_matches), 6)

    # 高burstiness奖励
    if burst > 0.5:
        result.reducer_bonus -= min(int((burst - 0.5) * 20), 8)

    # ─── 最终评分 ───
    raw = sum(result.dimension_scores.values())
    capped = min(raw, 100)
    final = max(0, capped + result.reducer_bonus)
    result.raw_score = raw
    result.final_score = final
    return result

# ─── 句子级评分 ───

def score_sentences(text, top_n=5):
    sentences = split_sentences(text)
    scored = []
    for s in sentences:
        score = 0
        reasons = []
        # 通用高权重
        for p in MECH_CONNECTORS:
            if p in s:
                score += 3
                reasons.append(p)
        for p in EMPTY_GRAND + AI_HIGH_FREQ:
            if p in s:
                score += 2
                reasons.append(p)
        for pat in THREE_PART_REGEX + TEMPLATE_REGEX:
            if re.search(pat, s, re.DOTALL):
                score += 5
                reasons.append(f'模板: {pat[:30]}')
        # 朱雀专项
        for p in ZQ_PERFECT_SUMMARY_PHRASES + ZQ_FUNC_PHRASES + ZQ_AI_VERBS:
            if re.search(p, s):
                score += 4
                reasons.append(p[:20])
        for pat in ZQ_CONSEC_RESULT_REGEX + ZQ_CONSEC_THROUGH_REGEX + ZQ_YISHI_REGEX:
            if re.search(pat, s, re.DOTALL):
                score += 8
                reasons.append('ZQ高危')
        if score > 0:
            scored.append((score, s, reasons))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_n]

# ─── 输出格式 ───

LEVEL_LABELS = {
    'LOW':       ('LOW',       0,  25),
    'MEDIUM':    ('MEDIUM',    25, 50),
    'HIGH':      ('HIGH',      50, 70),
    'VERY HIGH': ('VERY HIGH', 70, 100),
}

def get_level(score):
    if score < 25:
        return 'LOW'
    elif score < 50:
        return 'MEDIUM'
    elif score < 70:
        return 'HIGH'
    else:
        return 'VERY HIGH'

def bar(score, width=20):
    filled = int(score / 100 * width)
    return '█' * filled + '░' * (width - filled)

SEVERITY_ICON = {
    'critical': '🔴',
    'high':     '🟠',
    'medium':   '🟡',
    'low':      '⚪',
}

def format_report(result, verbose=False, top_sentences=5):
    lines = []
    score = result.final_score
    level = get_level(score)
    stats = result.stats

    lines.append(f'AI 评分: {score}/100 [{bar(score)}] {level}')
    lines.append(
        f'字符: {stats["chars"]} | 句子: {stats["sentences"]} | '
        f'平均句长: {stats["avg_sent_len"]}字 | 爆发度: {stats["burstiness"]}'
    )
    if stats.get('perplexity'):
        lines.append(
            f'困惑度: {stats["perplexity"]:.1f} | '
            f'熵: {stats["entropy"]} | '
            f'情感密度: {stats["emotion_density"]}%'
        )
    lines.append(f'问题总数: {len(result.issues)}')
    lines.append('')

    # 分类汇总
    by_cat = defaultdict(list)
    for iss in result.issues:
        by_cat[iss['category']].append(iss)

    for cat, items in sorted(by_cat.items(),
                              key=lambda x: -result.dimension_scores.get(x[0], 0)):
        icon = SEVERITY_ICON.get(items[0]['severity'], '⚪')
        lines.append(f'{icon} {cat} ({len(items)})')
        if verbose:
            for it in items[:2]:
                lines.append(f'   {it["description"]}')
                if it['snippet']:
                    lines.append(f'   → {it["snippet"]}')

    # 维度得分
    if verbose and result.dimension_scores:
        lines.append('')
        lines.append('── 各维度得分 ──')
        for dim, sc in sorted(result.dimension_scores.items(), key=lambda x: -x[1]):
            lines.append(f'  {dim}: {sc}')
        if result.reducer_bonus < 0:
            lines.append(f'  [降权补偿]: {result.reducer_bonus}')

    # 最可疑句子
    if top_sentences > 0:
        from io import StringIO
        buf = StringIO()
        # need original text to re-score — stored separately in caller
        pass

    return '\n'.join(lines)

# ─── CLI 入口 ───

def main():
    parser = argparse.ArgumentParser(description='中文 AI 文本检测 v1.0')
    parser.add_argument('file', nargs='?', help='输入文件路径（不指定则从 stdin 读取）')
    parser.add_argument('-j', '--json', action='store_true', help='JSON 输出')
    parser.add_argument('-s', '--score', action='store_true', help='仅输出分数')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细模式（含逐句分析）')
    parser.add_argument('--sentences', type=int, default=5, help='显示最可疑的 N 个句子')
    args = parser.parse_args()

    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if not text.strip():
        print('错误: 输入为空', file=sys.stderr)
        sys.exit(1)

    result = detect(text)
    top_sents = score_sentences(text, top_n=args.sentences)

    if args.score:
        print(result.final_score)
        return

    if args.json:
        out = {
            'score': result.final_score,
            'level': get_level(result.final_score),
            'stats': result.stats,
            'dimension_scores': result.dimension_scores,
            'reducer_bonus': result.reducer_bonus,
            'issues': result.issues,
            'top_sentences': [
                {'score': s, 'text': t, 'reasons': r}
                for s, t, r in top_sents
            ]
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # 普通输出
    print(format_report(result, verbose=args.verbose))

    if top_sents and args.sentences > 0:
        print('\n── 最可疑句子 ──')
        for i, (sc, sent, reasons) in enumerate(top_sents, 1):
            print(f'  {i}. [{sc}分] {sent[:70]}')
            if reasons:
                reason_str = ', '.join(str(r) for r in reasons[:3])
                print(f'     原因: {reason_str}')

if __name__ == '__main__':
    main()
