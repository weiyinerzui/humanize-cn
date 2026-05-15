#!/usr/bin/env python3
"""
rewrite_beam.py - L3 Adversarial Beam Search Rewrite Engine

Implements sentence-level beam search rewriting:
1. Split text into sentences
2. For each sentence, generate K candidate rewrites via LLM
3. Score each candidate with detect.py
4. Select the candidate with lowest AI score

Based on: Adversarial Paraphrasing (Sadasivan et al., NeurIPS 2025)
Adapted for API-based LLMs (sentence-level beam instead of token-level).
"""

import sys, os, re, time, argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from text_utils import split_sentences, merge_sentences
from rewrite import call_llm, call_with_retry, _clean_llm_output


# ─── Candidate Generation Prompts ───

BEAM_PROMPTS = {
    'academic': [
        '''改写以下句子，用更自然、更像人类写作的风格，同时保留学术含义。

要求：
- 改变句式结构（不要跟原文一样）
- 避免"值得注意的是""综上所述""然而"等机械连接词
- 保留专业术语和数据
- 可以使用更短或更长的句子

原文：{text}

请直接输出改写后的句子：''',
        '''以人类学者的口吻重写这句话，保持学术严谨性：

要求：
- 可以拆分或合并句子
- 避免AI写作套话
- 句式要有变化

原文：{text}

改写：''',
        '''用不同方式表达这句话：改变语序、调整从句位置、去掉冗余修饰词。保持原意。

原文：{text}

改写：''',
    ],
    'general': [
        '''用更口语化、更自然的方式改写，像普通人日常说话：

要求：
- 可以使用第一人称
- 不必太正式
- 可以更短

原文：{text}

改写：''',
        '''用完全不同的表达方式重写，像在跟朋友聊天：

原文：{text}

改写：''',
        '''让下面这句话听起来不那么机械，更像真人写的：

原文：{text}

改写：''',
    ],
}


def generate_candidates(sentence: str, mode: str = 'academic', k: int = 3,
                         model: str = None) -> list[str]:
    """Generate K diverse candidate rewrites for a sentence.

    Uses different prompt variants to produce diversity.
    Falls back gracefully on LLM errors.
    """
    prompts = BEAM_PROMPTS.get(mode, BEAM_PROMPTS['academic'])
    selected_prompts = [prompts[i % len(prompts)] for i in range(k)]

    candidates = []
    for prompt_template in selected_prompts:
        prompt = prompt_template.format(text=sentence)
        rewritten, err = call_with_retry(
            "你是文本改写助手。直接输出改写结果，不要加前缀说明。",
            prompt, model=model, retries=2, delay=3
        )
        if err:
            candidates.append(sentence)  # fallback to original
        else:
            cleaned = _clean_llm_output(rewritten)
            if cleaned and len(cleaned) > 2:
                candidates.append(cleaned)
            else:
                candidates.append(sentence)

    return candidates


def select_best(candidates: list[str], detect_scores: list[float]) -> str:
    """Select the candidate with the lowest AI detect score."""
    if not candidates:
        return ""
    paired = list(zip(candidates, detect_scores))
    paired.sort(key=lambda x: x[1])
    return paired[0][0]


def score_candidates(candidates: list[str]) -> list[float]:
    """Score each candidate using detect.py. Lower score = less AI-like."""
    from detect import detect as run_detect
    scores = []
    for c in candidates:
        try:
            result = run_detect(c)
            scores.append(result.final_score)
        except Exception:
            scores.append(100)  # worst score as fallback
    return scores


def beam_rewrite_sentence(sentence: str, mode: str = 'academic',
                          k: int = 3, model: str = None) -> list[str]:
    """Beam rewrite a single sentence: generate K candidates.

    Returns all candidates (caller picks best via select_best).
    """
    return generate_candidates(sentence, mode=mode, k=k, model=model)


def beam_rewrite(text: str, mode: str = 'academic', k: int = 3,
                 model: str = None, verbose: bool = False) -> str:
    """Full beam rewrite: split text into sentences, beam rewrite each.

    Args:
        text: Input text to rewrite
        mode: 'academic' or 'general'
        k: Number of beam candidates per sentence
        model: LLM model override
        verbose: Print progress

    Returns:
        Rewritten text
    """
    sentences = split_sentences(text)

    if not sentences:
        return text

    rewritten_sentences = []
    total = len(sentences)

    for i, sent in enumerate(sentences):
        if verbose:
            print(f'[beam] sentence {i+1}/{total}: {sent[:40]}...', file=sys.stderr)

        # Skip very short sentences (noise, terminators)
        if len(sent.strip()) < 4:
            rewritten_sentences.append(sent)
            continue

        # Generate candidates and score
        candidates = beam_rewrite_sentence(sent, mode=mode, k=k, model=model)

        if len(candidates) <= 1:
            rewritten_sentences.append(candidates[0] if candidates else sent)
            continue

        scores = score_candidates(candidates)
        best = select_best(candidates, scores)
        rewritten_sentences.append(best)

        if verbose:
            best_score = min(scores) if scores else '?'
            print(f'  scores: {scores} -> best={best_score}', file=sys.stderr)

    return merge_sentences(rewritten_sentences)


# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description='L3 Adversarial Beam Rewrite')
    parser.add_argument('file', nargs='?', help='Input file')
    parser.add_argument('--mode', choices=['academic', 'general'], default='academic')
    parser.add_argument('-k', type=int, default=3, help='Beam width (default 3)')
    parser.add_argument('--model', help='LLM model override')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-o', '--output', help='Output file')
    args = parser.parse_args()

    text = open(args.file, 'r', encoding='utf-8').read() if args.file else sys.stdin.read()
    if not text.strip():
        print('Error: empty input', file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    result = beam_rewrite(text, mode=args.mode, k=args.k, model=args.model,
                          verbose=args.verbose)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'Saved to: {args.output}')
    else:
        print(result)

    if args.verbose:
        print(f'\nBeam rewrite completed in {time.time()-t0:.1f}s', file=sys.stderr)


if __name__ == '__main__':
    main()