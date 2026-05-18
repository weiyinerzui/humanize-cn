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
from metrics.semantic_sim import compute_semantic_similarity


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


def generate_candidates(sentence: str, mode: str = 'academic', k: int = 5,
                         model: str = None, feedback_issues: list = None) -> list[str]:
    """Generate K diverse candidate rewrites for a sentence.

    Uses different prompt variants and temperature settings to produce diversity.
    Falls back gracefully on LLM errors.
    """
    prompts = BEAM_PROMPTS.get(mode, BEAM_PROMPTS['academic'])
    
    # Temperature schedule for diversity
    temps = [0.7, 0.7, 1.0, 1.0, 1.2]
    
    candidates = []
    for i in range(k):
        prompt_template = prompts[i % len(prompts)]
        temp = temps[i % len(temps)]
        
        prompt = prompt_template.format(text=sentence)
        if feedback_issues:
            feedback_str = "、".join(feedback_issues)
            prompt += f"\n\n[注意] 上次检测发现您的文本具有以下明显的 AI 特征：{feedback_str}。请在本次改写中彻底避免这些特征，打破固定句式！"

        rewritten, err = call_with_retry(
            "你是文本改写助手。直接输出改写结果，不要加前缀说明。",
            prompt, model=model, retries=2, delay=3, temperature=temp
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


def score_candidates(candidates: list[str], prev_sent: str = "", next_sent: str = "") -> list[float]:
    """Score each candidate using detect.py with context awareness. Lower score = less AI-like."""
    from detect import detect as run_detect
    scores = []
    for c in candidates:
        try:
            context = prev_sent + c + next_sent
            result = run_detect(context)
            scores.append(result.final_score)
        except Exception:
            scores.append(100)  # worst score as fallback
    return scores


def beam_rewrite_sentence(sentence: str, mode: str = 'academic',
                          k: int = 5, model: str = None, feedback_issues: list = None) -> list[str]:
    """Beam rewrite a single sentence: generate K candidates.

    Returns all candidates (caller picks best via select_best).
    """
    return generate_candidates(sentence, mode=mode, k=k, model=model, feedback_issues=feedback_issues)


def beam_rewrite(text: str, mode: str = 'academic', k: int = 5,
                 model: str = None, verbose: bool = False, feedback_issues: list = None) -> str:
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

        # Context window
        prev_sent = rewritten_sentences[-1] if len(rewritten_sentences) > 0 else ""
        next_sent = sentences[i+1] if i < total - 1 else ""

        # Skip very short sentences (noise, terminators)
        if len(sent.strip()) < 4:
            rewritten_sentences.append(sent)
            continue

        # Generate candidates and score
        candidates = beam_rewrite_sentence(sent, mode=mode, k=k, model=model, feedback_issues=feedback_issues)

        if len(candidates) <= 1:
            rewritten_sentences.append(candidates[0] if candidates else sent)
            continue

        valid_candidates = []
        for c in candidates:
            sim = compute_semantic_similarity(sent, c)
            if sim >= 0.60:
                valid_candidates.append(c)
            elif verbose:
                print(f'  [reject] sim={sim:.4f} for: {c[:20]}...', file=sys.stderr)

        if not valid_candidates:
            valid_candidates = [sent]

        scores = score_candidates(valid_candidates, prev_sent=prev_sent, next_sent=next_sent)
        best = select_best(valid_candidates, scores)
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