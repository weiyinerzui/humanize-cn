#!/usr/bin/env python3
"""
report.py - 改写对比报告生成器 v1.0

生成两种输出:
  1. {name}_report.txt  - 纯文本对比报告（终端可读）
  2. JSON 字典（供 humanize.py 集成使用）

用法:
  python3 report.py original.txt rewritten.txt
  python3 report.py original.txt rewritten.txt -o my_report.txt
  python3 report.py original.txt rewritten.txt -j  # JSON 输出
"""

import sys
import os
import re
import json
import argparse
import difflib
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── 工具函数 ───

def count_chinese(text):
    return len(re.findall(r'[\u4e00-\u9fff]', text))

def split_sentences(text):
    parts = re.split(r'([。！？；\n])', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i].strip()
        if s:
            sentences.append(s + parts[i+1])
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append(parts[-1].strip())
    return [s for s in sentences if len(s.strip()) > 2]

def sentence_lengths(text):
    return [count_chinese(s) for s in split_sentences(text) if count_chinese(s) > 0]

def avg_len(lengths):
    return round(sum(lengths) / len(lengths), 1) if lengths else 0

def burstiness(lengths):
    if len(lengths) < 3:
        return 0.0
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.0
    std = (sum((x - mean)**2 for x in lengths) / len(lengths)) ** 0.5
    return round(std / mean, 3)

def char_similarity(a, b):
    """基于字符的相似度（difflib）"""
    sm = difflib.SequenceMatcher(None, a, b)
    return round(sm.ratio(), 3)

def changed_ratio(a, b):
    """改动比例 = 1 - 相似度"""
    return round(1 - char_similarity(a, b), 3)

def count_cliches(text):
    """计算套话数量（用于衡量降AI效果）"""
    CLICHE_WORDS = [
        '综上所述','不难发现','值得注意的是','与此同时','在此基础上',
        '由此可见','不仅如此','换句话说','更重要的是','需要强调的是',
        '首先','其次','最后','毫无疑问','显而易见',
        '取得了显著成效','奠定了坚实基础','具有重要意义',
        '赋能','闭环','深度融合','协同增效',
        '通过.*?实现', '借助.*?构建',
    ]
    count = 0
    for w in CLICHE_WORDS:
        if '.*' in w:
            count += len(re.findall(w, text))
        else:
            count += text.count(w)
    return count

# ─── 核心统计 ───

def compute_stats(text):
    lengths = sentence_lengths(text)
    chars = count_chinese(text)
    sents = len(split_sentences(text))
    return {
        'chars': chars,
        'sentences': sents,
        'avg_sent_len': avg_len(lengths),
        'burstiness': burstiness(lengths),
        'cliche_count': count_cliches(text),
    }

def run_detect(text):
    """尝试调用 detect.py 评分，失败则返回 None"""
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from detect import detect, get_level
        result = detect(text)
        return {
            'score': result.final_score,
            'level': get_level(result.final_score),
            'dimension_scores': result.dimension_scores,
            'issues': result.issues,
        }
    except Exception as e:
        return {'score': None, 'level': 'N/A', 'error': str(e)}

# ─── 差异分析 ───

def sentence_diff(orig_text, rewr_text):
    """句子级差异：返回 (unchanged, changed, added, removed)"""
    orig_sents = set(split_sentences(orig_text))
    rewr_sents = set(split_sentences(rewr_text))
    unchanged = orig_sents & rewr_sents
    changed   = rewr_sents - orig_sents   # 新出现（可能是改写后的）
    removed   = orig_sents - rewr_sents   # 原文有、改写后没有
    return len(unchanged), len(changed), len(removed)

def sample_changes(orig_text, rewr_text, n=3):
    """抽取 n 对有代表性的改动示例（原句 -> 新句）"""
    orig_sents = split_sentences(orig_text)
    rewr_sents = split_sentences(rewr_text)
    # 用 difflib 匹配最相似的句子对
    examples = []
    used_rewr = set()
    for orig in orig_sents:
        best_score = 0
        best_rewr = None
        for i, rewr in enumerate(rewr_sents):
            if i in used_rewr:
                continue
            score = difflib.SequenceMatcher(None, orig, rewr).ratio()
            if 0.3 < score < 0.95 and score > best_score:
                best_score = score
                best_rewr = (i, rewr)
        if best_rewr:
            used_rewr.add(best_rewr[0])
            examples.append((orig, best_rewr[1], round(best_score, 2)))
            if len(examples) >= n:
                break
    return examples

# ─── 报告生成 ───

SEPARATOR = '─' * 60

def bar(val, max_val=100, width=20, char='█'):
    if max_val == 0:
        return '░' * width
    filled = int(val / max_val * width)
    return char * filled + '░' * (width - filled)

def format_text_report(orig_text, rewr_text, mode, intensity, model,
                        rewrite_error=None, title=None,
                        orig_detect=None, rewr_detect=None):
    """生成纯文本报告字符串"""

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    orig_stats = compute_stats(orig_text)
    rewr_stats = compute_stats(rewr_text)

    # detect 评分（使用传入的结果，避免重复计算）
    if orig_detect is None:
        orig_detect = run_detect(orig_text)
    if rewr_detect is None:
        rewr_detect = run_detect(rewr_text) if not rewrite_error else {'score': None, 'level': 'N/A'}

    # 改动量
    change_ratio = changed_ratio(orig_text, rewr_text)
    unchanged_n, changed_n, removed_n = sentence_diff(orig_text, rewr_text)
    examples = sample_changes(orig_text, rewr_text, n=3)

    lines = []

    # ── 标题 ──
    lines.append('=' * 60)
    lines.append(f'  humanize-cn 改写报告')
    if title:
        lines.append(f'  文件: {title}')
    lines.append(f'  时间: {now}')
    lines.append(f'  模式: {mode}  强度: {intensity}  模型: {model}')
    lines.append('=' * 60)

    # ── 错误 ──
    if rewrite_error:
        lines.append(f'\n[错误] 改写失败: {rewrite_error}')
        lines.append('报告仅显示原文检测结果，改写列为 N/A\n')

    # ── AI 评分对比 ──
    lines.append(SEPARATOR)
    lines.append('  AI 检测评分对比')
    lines.append(SEPARATOR)

    orig_score = orig_detect.get('score')
    rewr_score = rewr_detect.get('score')

    def fmt_score(s, level):
        if s is None:
            return 'N/A'
        return f'{s}/100 [{bar(s)}] {level}'

    lines.append(f'  原文评分:  {fmt_score(orig_score, orig_detect.get("level",""))}')
    lines.append(f'  改写评分:  {fmt_score(rewr_score, rewr_detect.get("level",""))}')

    if orig_score is not None and rewr_score is not None:
        delta = orig_score - rewr_score
        sign = '-' if delta >= 0 else '+'
        lines.append(f'  分数变化:  {sign}{abs(delta)} 分 ({"降低" if delta>=0 else "升高"})')
        if delta >= 20:
            lines.append('  评估: ✅ 改写效果显著（降分 ≥ 20）')
        elif delta >= 10:
            lines.append('  评估: 🟡 改写有效，可再次运行进一步降低')
        elif delta > 0:
            lines.append('  评估: 🟠 改写效果有限，建议用 aggressive 模式重试')
        else:
            lines.append('  评估: 🔴 改写后评分未降低，请检查输出质量')

    # ── 文本统计对比 ──
    lines.append('')
    lines.append(SEPARATOR)
    lines.append('  文本统计对比')
    lines.append(SEPARATOR)
    lines.append(f'  {"指标":<14} {"原文":>8} {"改写":>8} {"变化":>8}')
    lines.append(f'  {"-"*14} {"-"*8} {"-"*8} {"-"*8}')

    def diff_str(a, b):
        if a is None or b is None:
            return 'N/A'
        d = b - a
        return f'+{d}' if d > 0 else str(d)

    lines.append(f'  {"字数":<14} {orig_stats["chars"]:>8} {rewr_stats["chars"]:>8} '
                 f'{diff_str(orig_stats["chars"], rewr_stats["chars"]):>8}')
    lines.append(f'  {"句子数":<14} {orig_stats["sentences"]:>8} {rewr_stats["sentences"]:>8} '
                 f'{diff_str(orig_stats["sentences"], rewr_stats["sentences"]):>8}')
    lines.append(f'  {"平均句长":<14} {orig_stats["avg_sent_len"]:>8} {rewr_stats["avg_sent_len"]:>8} '
                 f'{diff_str(orig_stats["avg_sent_len"], rewr_stats["avg_sent_len"]):>8}')
    lines.append(f'  {"爆发度":<14} {orig_stats["burstiness"]:>8} {rewr_stats["burstiness"]:>8} '
                 f'{diff_str(orig_stats["burstiness"], rewr_stats["burstiness"]):>8}')
    lines.append(f'  {"套话数":<14} {orig_stats["cliche_count"]:>8} {rewr_stats["cliche_count"]:>8} '
                 f'{diff_str(orig_stats["cliche_count"], rewr_stats["cliche_count"]):>8}')
    lines.append(f'  {"文本改动率":<14} {"":>8} {change_ratio*100:.1f}%')

    # ── 句子改动统计 ──
    lines.append('')
    lines.append(SEPARATOR)
    lines.append('  句子改动分析')
    lines.append(SEPARATOR)
    lines.append(f'  未改动句子: {unchanged_n}')
    lines.append(f'  改动/新增:  {changed_n}')
    lines.append(f'  删除句子:   {removed_n}')

    # ── 改动示例 ──
    if examples:
        lines.append('')
        lines.append(SEPARATOR)
        lines.append('  改动示例（相似度 0.3~0.95 的句对）')
        lines.append(SEPARATOR)
        for i, (orig_s, rewr_s, sim) in enumerate(examples, 1):
            lines.append(f'  [{i}] 相似度 {sim}')
            lines.append(f'  原: {orig_s[:70]}{"…" if len(orig_s)>70 else ""}')
            lines.append(f'  新: {rewr_s[:70]}{"…" if len(rewr_s)>70 else ""}')
            lines.append('')

    # ── 维度得分变化 ──
    if (orig_detect.get('dimension_scores') and
            rewr_detect.get('dimension_scores')):
        lines.append(SEPARATOR)
        lines.append('  各维度得分变化')
        lines.append(SEPARATOR)
        orig_dims = orig_detect['dimension_scores']
        rewr_dims = rewr_detect['dimension_scores']
        all_dims = sorted(set(list(orig_dims.keys()) + list(rewr_dims.keys())),
                          key=lambda d: -orig_dims.get(d, 0))
        for dim in all_dims[:8]:  # 只展示前8个
            o = orig_dims.get(dim, 0)
            r = rewr_dims.get(dim, 0)
            delta = r - o
            sign = '+' if delta > 0 else ''
            icon = '✅' if delta < 0 else ('🔴' if delta > 0 else '⚪')
            lines.append(f'  {icon} {dim:<20} {o:>4} → {r:>4}  ({sign}{delta})')

    # ── 建议 ──
    lines.append('')
    lines.append(SEPARATOR)
    lines.append('  后续建议')
    lines.append(SEPARATOR)
    if rewr_score is not None:
        if rewr_score >= 60:
            lines.append('  1. 评分仍较高，建议再次运行 --intensity aggressive')
            lines.append('  2. 重点关注: 连续成果罗列、三段式结构')
            lines.append('  3. 可手动拆分/合并最可疑的 2-3 个句子')
        elif rewr_score >= 30:
            lines.append('  1. 分数较好，可直接提交检测验证')
            lines.append('  2. 如知网/维普仍报 AIGC，重点改写"最可疑句子"')
        else:
            lines.append('  1. 分数较低，有较大概率通过 AIGC 检测')
            lines.append('  2. 提交前建议在朱雀/知网实测确认')
    lines.append('  （人工校验：重点看数据/术语是否原样保留）')
    lines.append('')
    lines.append('=' * 60)

    return '\n'.join(lines)


def generate_report(orig_text, rewr_text, mode='academic', intensity='conservative',
                    model='unknown', rewrite_error=None, title=None):
    """
    生成报告，返回 dict:
    {
        'text_report': str,   # 纯文本报告
        'json_data':   dict,  # 结构化数据
    }
    """
    orig_stats  = compute_stats(orig_text)
    rewr_stats  = compute_stats(rewr_text)
    orig_detect = run_detect(orig_text)
    rewr_detect = run_detect(rewr_text) if not rewrite_error else {'score': None, 'level': 'N/A'}
    change      = changed_ratio(orig_text, rewr_text)
    examples    = sample_changes(orig_text, rewr_text, n=3)

    text_report = format_text_report(
        orig_text, rewr_text, mode, intensity, model, rewrite_error, title,
        orig_detect=orig_detect, rewr_detect=rewr_detect
    )

    json_data = {
        'meta': {
            'mode': mode,
            'intensity': intensity,
            'model': model,
            'title': title,
            'rewrite_error': rewrite_error,
        },
        'original': {
            'stats': orig_stats,
            'detect': orig_detect,
        },
        'rewritten': {
            'stats': rewr_stats,
            'detect': rewr_detect,
        },
        'diff': {
            'char_change_ratio': change,
            'score_delta': (
                (orig_detect.get('score') or 0) - (rewr_detect.get('score') or 0)
                if orig_detect.get('score') is not None and rewr_detect.get('score') is not None
                else None
            ),
            'examples': [
                {'original': o, 'rewritten': r, 'similarity': s}
                for o, r, s in examples
            ],
        },
    }

    return {'text_report': text_report, 'json_data': json_data}


def save_report(text_report, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text_report)

# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description='改写对比报告生成器 v1.0')
    parser.add_argument('original',  help='原始文件路径')
    parser.add_argument('rewritten', help='改写后文件路径')
    parser.add_argument('-o', '--output', help='报告输出路径（默认打印到 stdout）')
    parser.add_argument('-j', '--json', action='store_true', help='JSON 输出')
    parser.add_argument('--mode',      default='academic')
    parser.add_argument('--intensity', default='conservative')
    parser.add_argument('--model',     default='unknown')
    args = parser.parse_args()

    with open(args.original,  'r', encoding='utf-8') as f:
        orig_text = f.read()
    with open(args.rewritten, 'r', encoding='utf-8') as f:
        rewr_text = f.read()

    title = os.path.basename(args.original)
    result = generate_report(
        orig_text, rewr_text,
        mode=args.mode, intensity=args.intensity,
        model=args.model, title=title
    )

    if args.json:
        print(json.dumps(result['json_data'], ensure_ascii=False, indent=2))
        return

    out = result['text_report']
    if args.output:
        save_report(out, args.output)
        print(f'报告已保存: {args.output}')
    else:
        print(out)

if __name__ == '__main__':
    main()
