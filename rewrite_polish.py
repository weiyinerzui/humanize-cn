#!/usr/bin/env python3
"""
rewrite_polish.py - L1 Rule-Based Polish Engine

Post-processes beam-rewritten text to clean residual AI patterns:
1. Replace mechanical connectors with natural alternatives
2. Remove empty filler phrases
3. Vary sentence length patterns to increase burstiness
"""

import re, random

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


def replace_mechanical_connectors(text: str) -> str:
    """Replace AI-typical mechanical connectors with alternatives."""
    for pattern, alternatives in CONNECTOR_MAP.items():
        if pattern in text:
            replacement = random.choice(alternatives)
            text = text.replace(pattern, replacement, 1)
    return text


def _clean_whitespace(text: str) -> str:
    """Clean up double spaces and excessive newlines."""
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def polish(text: str, mode: str = 'academic') -> str:
    """Apply L1 post-processing to clean residual AI patterns.

    Args:
        text: Beam-rewritten text
        mode: 'academic' or 'general'

    Returns:
        Polished text
    """
    if not text or not text.strip():
        return ""

    # Step 1: Replace mechanical connectors
    text = replace_mechanical_connectors(text)

    # Step 2: Clean whitespace
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