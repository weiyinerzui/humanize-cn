#!/usr/bin/env python3
"""
humanize.py - 统一入口 v1.0
编排 detect → rewrite → report 三阶段流水线

输出两个文件:
  {basename}_rewritten.txt  - 改写后正文
  {basename}_report.txt     - 对比报告

用法:
  python3 humanize.py 论文片段.txt
  python3 humanize.py 论文片段.txt --mode academic
  python3 humanize.py 论文片段.txt --mode general --intensity aggressive
  python3 humanize.py 论文片段.txt --rounds 2        # 多轮改写
  python3 humanize.py 论文片段.txt --detect-only      # 只检测，不改写
  python3 humanize.py 论文片段.txt --dry-run          # 显示 prompt，不调用 LLM
  echo "文本" | python3 humanize.py                   # stdin（输出到 stdout）

环境变量 / .env:
  CF_ACCOUNT_ID  CF_API_TOKEN  CF_MODEL
"""

import sys
import os
import re
import json
import time
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from detect  import detect as run_detect, get_level, score_sentences, format_report
from rewrite import rewrite as run_rewrite
from report  import generate_report, save_report
from rewrite_beam import beam_rewrite
from rewrite_polish import polish

# ─── 工具函数 ───

def make_output_path(input_path, suffix):
    base = os.path.splitext(input_path)[0]
    return f'{base}_{suffix}'

def print_banner(text=''):
    print('=' * 60)
    if text:
        print(f'  {text}')
        print('=' * 60)

def print_section(text):
    print(f'\n── {text} ──')

def detect_and_print(text, label='检测结果', verbose=False):
    """运行 detect 并打印摘要，返回 DetectionResult"""
    result = run_detect(text)
    level  = get_level(result.final_score)
    print(f'  {label}: {result.final_score}/100  [{level}]')
    if verbose:
        print(format_report(result, verbose=True))
    else:
        # 打印 top 问题
        from collections import defaultdict
        by_cat = defaultdict(int)
        for iss in result.issues:
            by_cat[iss['category']] += 1
        if by_cat:
            top = sorted(by_cat.items(), key=lambda x: -x[1])[:4]
            print('  主要问题: ' + '  '.join(f'{c}({n})' for c, n in top))
    return result

# ─── 主流程 ───

def pipeline(text, mode='academic', intensity=None, model=None,
             rounds=1, dry_run=False, verbose=False, detect_only=False,
             beam_k=3, polish_enabled=True,
             input_path=None, output_dir=None):
    """
    五阶段流水线 v2.0 — Adversarial Beam

    Phase 1: detect (基线评分)
    Phase 2: L3 beam search 改写
    Phase 3: L1 rule-based 精修
    Phase 4: detect (改写后评分)
    Phase 5: report (对比报告)

    返回:
        dict: {
            'original':        str,
            'rewritten':       str,
            'detect_before':   DetectionResult,
            'detect_after':    DetectionResult | None,
            'rewrite_result':  dict,
            'report':          dict,
            'output_rewritten': str | None,  # 保存路径
            'output_report':    str | None,
        }
    """
    print_banner('humanize-cn  降AI改写系统 v2.0')

    # ─── Phase 1: 检测 ───
    print_section('Phase 1  检测')
    t0 = time.time()
    detect_before = detect_and_print(text, label='原文评分', verbose=verbose)
    print(f'  耗时: {time.time()-t0:.1f}s')

    if detect_only:
        return {
            'original': text,
            'detect_before': detect_before,
            'detect_after': None,
            'rewritten': text,
            'rewrite_result': {},
            'report': {},
            'output_rewritten': None,
            'output_report': None,
        }

    if detect_before.final_score < 20:
        print('  AI味较低，可能不需要改写。继续执行改写…')

    # ─── Phase 2: L3 Beam Search 改写 ───
    print_section(f'Phase 2  L3 Beam Search 改写 (K={beam_k})')
    t1 = time.time()
    rewrite_result = {}
    if dry_run:
        rewritten_text = text
        rewrite_result = {'dry_run': True}
        print('  [DRY RUN] 跳过 LLM 调用')
    else:
        rewritten_text = beam_rewrite(text, mode=mode, k=beam_k,
                                       model=model, verbose=verbose)
        rewrite_result = {'model': model or 'deepseek/deepseek-v4-pro', 'error': None}
    print(f'  Beam rewrite 完成  耗时: {time.time()-t1:.1f}s')

    # ─── Phase 3: L1 精修 ───
    if polish_enabled and not dry_run:
        print_section('Phase 3  L1 精修')
        t2 = time.time()
        rewritten_text = polish(rewritten_text, mode=mode)
        print(f'  精修完成  耗时: {time.time()-t2:.1f}s')
    elif dry_run:
        print_section('Phase 3  L1 精修 [DRY RUN 跳过]')

    # ─── Phase 4: 改写后检测 ───
    print_section('Phase 4  改写后检测')
    if not dry_run:
        detect_after = run_detect(rewritten_text)
        score_after = detect_after.final_score
        score_before = detect_before.final_score
        delta = score_before - score_after
        print(f'  原文: {score_before}/100  →  改写: {score_after}/100  (变化: {"-" if delta>=0 else "+"}{abs(delta)}分)')
        if score_after < 30:
            print('  ✅ 评分低于30，有较大概率通过AIGC检测')
        elif score_after < 50:
            print('  🟡 评分中等，建议提交朱雀验证后酌情再次改写')
        else:
            print('  🟠 评分仍较高，建议增加 --beam-k 或提交朱雀验证')
    else:
        detect_after = None

    # ─── Phase 5: 报告 ───
    print_section('Phase 5  报告')
    t3 = time.time()
    report = generate_report(
        text,
        rewritten_text,
        mode=mode,
        intensity='beam',
        model=rewrite_result.get('model', 'unknown') if rewrite_result else 'unknown',
        rewrite_error=rewrite_result.get('error') if rewrite_result else None,
        title=os.path.basename(input_path) if input_path else None,
    )
    print(f'  报告生成耗时: {time.time()-t3:.1f}s')

    # ─── 保存输出文件 ───
    output_rewritten = None
    output_report    = None

    if input_path and not dry_run:
        base = os.path.splitext(input_path)[0]
        if output_dir:
            base = os.path.join(output_dir, os.path.basename(base))
            os.makedirs(output_dir, exist_ok=True)

        output_rewritten = f'{base}_rewritten.txt'
        output_report    = f'{base}_report.txt'

        with open(output_rewritten, 'w', encoding='utf-8') as f:
            f.write(rewritten_text)
        save_report(report['text_report'], output_report)

        print_section('输出文件')
        print(f'  改写文本: {output_rewritten}')
        print(f'  对比报告: {output_report}')

    print_banner('完成')

    return {
        'original':        text,
        'rewritten':       rewritten_text,
        'detect_before':   detect_before,
        'detect_after':    detect_after,
        'rewrite_result':  rewrite_result,
        'report':          report,
        'output_rewritten': output_rewritten,
        'output_report':    output_report,
    }

# ─── detect-only 模式 ───

def detect_only(text, verbose=False):
    """只运行检测，打印详细报告"""
    result = run_detect(text)
    print(format_report(result, verbose=verbose))
    print()
    top_sents = score_sentences(text, top_n=5)
    if top_sents:
        print('── 最可疑句子 ──')
        for i, (sc, sent, reasons) in enumerate(top_sents, 1):
            print(f'  {i}. [{sc}分] {sent[:70]}')
            if reasons:
                print(f'     原因: {", ".join(str(r) for r in reasons[:3])}')
    return result

# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(
        description='humanize-cn 降AI改写系统 v1.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 humanize.py 论文.txt
  python3 humanize.py 论文.txt --mode academic --intensity aggressive
  python3 humanize.py 论文.txt --rounds 2
  python3 humanize.py 论文.txt --detect-only -v
  echo "文本" | python3 humanize.py --mode general
        """
    )
    parser.add_argument('file', nargs='?', help='输入文件（不指定则从 stdin 读）')
    parser.add_argument('--mode', choices=['academic', 'general'], default='academic',
                        help='改写模式（默认 academic）')
    parser.add_argument('--intensity', choices=['conservative', 'aggressive'],
                        help='改写强度（默认自动：score≥60用aggressive）')
    parser.add_argument('--model', help='LLM 模型（默认 .env/CF_MODEL）')
    parser.add_argument('--rounds', type=int, default=1,
                        help='改写轮数（默认1，最多3）')
    parser.add_argument('--beam-k', type=int, default=3,
                        help='Beam width: 每句候选改写数（默认3）')
    parser.add_argument('--no-polish', action='store_true',
                        help='跳过 L1 精修阶段')
    parser.add_argument('--output-dir', help='输出目录（默认与输入文件同目录）')
    parser.add_argument('--detect-only', action='store_true',
                        help='只运行检测，不改写')
    parser.add_argument('--dry-run', action='store_true',
                        help='打印 prompt，不调用 LLM')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='详细输出（含各维度得分）')
    parser.add_argument('-j', '--json', action='store_true',
                        help='以 JSON 格式输出报告（调试用）')
    args = parser.parse_args()

    # 读取输入
    input_path = None
    if args.file:
        input_path = args.file
        with open(args.file, 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if not text.strip():
        print('错误: 输入为空', file=sys.stderr)
        sys.exit(1)

    # detect-only 模式
    if args.detect_only:
        detect_only(text, verbose=args.verbose)
        return

    # 限制 rounds
    rounds = min(max(1, args.rounds), 3)

    result = pipeline(
        text,
        mode=args.mode,
        intensity=args.intensity,
        model=args.model,
        rounds=rounds,
        beam_k=args.beam_k,
        polish_enabled=not args.no_polish,
        dry_run=args.dry_run,
        verbose=args.verbose,
        input_path=input_path,
        output_dir=args.output_dir,
    )

    # stdin 模式：输出到 stdout
    if not input_path:
        print('\n── 改写结果 ──')
        print(result['rewritten'])

    # JSON 输出
    if args.json:
        json_data = result['report']['json_data']
        print(json.dumps(json_data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
