#!/usr/bin/env python3
"""
rewrite_polish.py - L1 Rule-Based Polish Engine

Post-processes beam-rewritten text to clean residual AI patterns:
1. Replace mechanical connectors with natural alternatives
2. Second-pass academic cliché cleanup
3. Burstiness injection (sentence splitting/merging)
4. Imperfection injection
5. Sentence structure variation
6. Whitespace cleanup
"""

import re, random
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from text_utils import split_sentences, merge_sentences

# ─── Mechanical Connector Replacements ───

CONNECTOR_MAP = {
    '值得注意的是': ['需要注意的是', '值得关注的是', '应指出的是'],
    '综上所述': ['总的来说', '总体来看', '概括而言'],
    '与此同时': ['同时', '另外', '另一方面'],
    '由此可见': ['可见', '这表明', '这显示'],
    '不仅如此': ['而且', '再者', '更重要的是'],
    '不可否认': ['确实', '必须承认', '无可否认'],
    '总而言之': ['总之', '概括来说', '简而言之'],
    '不难发现': ['可以发现', '可见', '明显看出'],
    '显而易见': ['很明显', '显然', '清楚的是'],
    '归根结底': ['本质上', '说到底', '根本在于'],
    '换言之': ['也就是说', '换句话说', '或者说'],
    '需要强调的是': ['重点是', '关键是', '核心是'],
    '在此基础上': ['基于此', '以此为基础', '在这一前提下'],
}

ACADEMIC_CLICHES = [
    '研究表明', '具有重要意义', '取得了显著的成效', 
    '具有广阔的应用前景', '发挥着重要作用', '引起了广泛关注',
    '得到了广泛的应用', '提供了有力的支撑', '奠定了坚实的基础'
]

def replace_mechanical_connectors(text: str) -> str:
    for pattern, alternatives in CONNECTOR_MAP.items():
        if pattern in text:
            replacement = random.choice(alternatives)
            text = text.replace(pattern, replacement, 1)
    return text

def cleanup_academic_cliches(text: str) -> str:
    """Step 2: Second-pass academic cliché cleanup"""
    for cliche in ACADEMIC_CLICHES:
        if cliche in text:
            text = text.replace(cliche, '')
    # Fix broken punctuation from removals
    text = re.sub(r'，\s*，', '，', text)
    text = re.sub(r'，\s*。', '。', text)
    return text

def inject_burstiness(text: str) -> str:
    """Step 3: Burstiness injection. Break long sequences of similar length sentences."""
    sentences = split_sentences(text)
    if len(sentences) < 3:
        return text
        
    for i in range(len(sentences)):
        # Very naive split for extremely long sentences (>80 chars) to increase variance
        s = sentences[i]
        if len(s) > 80 and '，' in s[30:-30]:
            parts = s.split('，')
            mid = len(parts) // 2
            s1 = '，'.join(parts[:mid]) + '。'
            s2 = '此外，' + '，'.join(parts[mid:])
            if not s2.endswith('。') and not s2.endswith('！') and not s2.endswith('？'):
                if s2.endswith('；'):
                    s2 = s2[:-1] + '。'
                else:
                    s2 += '。'
            sentences[i] = s1 + s2
            
    return merge_sentences(sentences)

def inject_imperfection(text: str) -> str:
    """Step 4: Imperfection injection at the end of text"""
    if len(text) > 50 and ('实现' in text[-50:] or '发展' in text[-50:] or '成效' in text[-50:]):
        imperfections = [
            "当然，这在实际落地中仍面临一定挑战。",
            "不过，具体的实施细节仍有待进一步探讨。",
            "但不可否认，这一过程也存在不可预见的局限性。"
        ]
        text += random.choice(imperfections)
    return text

def vary_sentence_structure(text: str) -> str:
    """Step 5: Sentence structure variation. Naive passive voice injection"""
    if "通过" in text and "实现" in text:
        text = text.replace("通过", "借由", 1)
    return text

def _clean_whitespace(text: str) -> str:
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def polish(text: str, mode: str = 'academic') -> str:
    if not text or not text.strip():
        return ""

    text = replace_mechanical_connectors(text)
    text = cleanup_academic_cliches(text)
    text = inject_burstiness(text)
    text = inject_imperfection(text)
    text = vary_sentence_structure(text)
    text = _clean_whitespace(text)

    return text.strip()

# ─── CLI ───

def main():
    import argparse, sys
    parser = argparse.ArgumentParser(description='L1 Polish Engine')
    parser.add_argument('file', nargs='?', help='Input file')
    parser.add_argument('--mode', choices=['academic', 'general'], default='academic')
    parser.add_argument('-o', '--output', help='Output file')
    args = parser.parse_args()

    text = open(args.file, 'r', encoding='utf-8').read() if args.file else sys.stdin.read()
    result = polish(text, mode=args.mode)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'Saved to: {args.output}')
    else:
        print(result)

if __name__ == '__main__':
    main()