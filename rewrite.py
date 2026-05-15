#!/usr/bin/env python3
"""rewrite.py - LLM 改写引擎 v2.0 · 七牛云 QnAIGC 后端"""

import sys, os, re, json, argparse, urllib.request, urllib.error, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_env():
    env_file = os.path.join(SCRIPT_DIR, '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

# ─── 默认配置 · 七牛云 QnAIGC ───
QN_BASE_URL = os.environ.get('QN_BASE_URL', 'https://api.qnaigc.com/v1')
QN_API_KEY = os.environ.get('QN_API_KEY', '') or os.environ.get('QNAIGC_API_TOKEN', '')
QN_MODEL    = os.environ.get('QN_MODEL', '') or os.environ.get('MODEL_ID', 'deepseek/deepseek-v4-pro')

PROMPTS = {}

def load_prompt(mode):
    if mode not in PROMPTS:
        path = os.path.join(SCRIPT_DIR, 'prompts', f'{mode}.txt')
        if not os.path.exists(path):
            raise FileNotFoundError(f'找不到 prompt 文件: {path}')
        with open(path, 'r', encoding='utf-8') as f:
            PROMPTS[mode] = f.read()
    return PROMPTS[mode]

INTENSITY_DESCRIPTION = {
    'conservative': '保守改写：只改写评分最高的句子（top 3），保留其余原文。……',
    'aggressive':   '激进改写：对全文进行深度重构，目标 AIGC 率降至 25% 以下。……',
}

def get_intensity(score):
    return 'aggressive' if score >= 60 else 'conservative'

# ─── LLM 调用（OpenAI 兼容格式）───

def call_llm(system_prompt, user_text, model=None, max_tokens=4096, timeout=120):
    model = model or QN_MODEL
    api_key = QN_API_KEY
    base_url = QN_BASE_URL

    if not api_key:
        return None, 'QN_API_KEY 未设置。请在 humanize-cn/.env 中配置。'

    url = f'{base_url}/chat/completions'
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user',   'content': user_text},
        ],
        'max_tokens': max_tokens,
        'temperature': 0.85,
        'top_p':       0.9,
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {api_key}',
        'Content-Type':  'application/json',
    }, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        if 'choices' in body:
            text = body['choices'][0]['message']['content']
        elif 'result' in body:
            r = body['result']
            text = r.get('response') or r.get('content', str(r)) if isinstance(r, dict) else str(r)
        else:
            return None, f'未知响应: {json.dumps(body, ensure_ascii=False)[:200]}'
        return text.strip(), None
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return None, f'HTTP {e.code}: {body[:300]}'
    except urllib.error.URLError as e:
        return None, f'网络错误: {e.reason}'
    except Exception as e:
        return None, f'未知错误: {e}'

def call_with_retry(*args, retries=3, delay=5, **kwargs):
    for attempt in range(retries):
        text, err = call_llm(*args, **kwargs)
        if text is not None:
            return text, None
        if attempt < retries - 1:
            print(f'[rewrite] 第{attempt+1}次失败: {err}，{delay}s 后重试…', file=sys.stderr)
            time.sleep(delay)
    return None, err

# ─── Prompt 构建 ───

def build_system_prompt(mode, intensity, top_sentences=None):
    template = load_prompt(mode)
    intensity_desc = INTENSITY_DESCRIPTION.get(intensity, INTENSITY_DESCRIPTION['conservative'])
    if top_sentences:
        sent_lines = '\n'.join(f'{i+1}. [风险{sc}分] {t[:60]}{"…" if len(t)>60 else ""}'
                               for i, (sc, t, _) in enumerate(top_sentences[:5]))
    else:
        sent_lines = '（无句子级评分数据）'
    prompt = template.replace('{INTENSITY}', intensity_desc).replace('{TOP_SENTENCES}', sent_lines)
    return prompt

def _clean_llm_output(text):
    """清理 LLM 输出中的前缀和后缀"""
    for pat in [r'^改写[如后].*?[：:]\s*\n?', r'^以下是改写.*?[：:]\s*\n?',
                r'^好的[，,].*?[：:]\s*\n?', r'^根据.*?改写如下.*?[：:]\s*\n?']:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r'\n[-—=]{3,}\s*$', '', text.rstrip())
    text = re.sub(r'\n（完）\s*$', '', text.rstrip())
    return text.strip()

# ─── 本地替换引擎（加载 JSON 替换词库）───

_REPLACEMENTS_CACHE = None

def _load_replacements():
    """加载 patterns_base.json 中的 replacements + academic_patterns.replacements"""
    global _REPLACEMENTS_CACHE
    if _REPLACEMENTS_CACHE is not None:
        return _REPLACEMENTS_CACHE

    path = os.path.join(SCRIPT_DIR, 'patterns', 'patterns_base.json')
    _REPLACEMENTS_CACHE = {}
    if not os.path.exists(path):
        return _REPLACEMENTS_CACHE
    with open(path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    # 通用替换
    for key, vals in cfg.get('replacements', {}).items():
        if isinstance(vals, list) and vals:
            _REPLACEMENTS_CACHE[key] = vals
    # 学术替换
    for key, vals in cfg.get('academic_patterns', {}).get('replacements', {}).items():
        if key == 'description':
            continue
        if isinstance(vals, list) and vals:
            _REPLACEMENTS_CACHE[key] = vals

    return _REPLACEMENTS_CACHE

def apply_replacements(text, mode='academic'):
    """
    用 patterns_base.json 中的替换词库对文本做一轮本地替换。
    每个匹配随机选择一个替换项，避免千篇一律。
    """
    import random
    replacements = _load_replacements()
    if not replacements:
        return text

    # 按匹配长度倒排，优先替换更长的短语
    sorted_keys = sorted(replacements.keys(), key=len, reverse=True)
    for pattern in sorted_keys:
        alternatives = replacements[pattern]
        if not alternatives:
            continue
        # 如果 pattern 含正则元字符（.*等），用 re.sub
        if any(c in pattern for c in r'.*+?()[]{}\\'):
            try:
                replacement = random.choice(alternatives)
                text = re.sub(pattern, replacement, text, count=1)
            except re.error:
                pass
        else:
            if pattern in text:
                replacement = random.choice(alternatives)
                text = text.replace(pattern, replacement, 1)
    return text

# ─── 改写主函数 ───

def rewrite(text, mode='academic', intensity=None, detect_result=None,
            model=None, dry_run=False, verbose=False):
    if intensity is None:
        intensity = get_intensity(detect_result.final_score) if detect_result else 'conservative'
    model = model or QN_MODEL

    top_sents = None
    dim_scores_hint = ''
    if detect_result:
        try:
            sys.path.insert(0, SCRIPT_DIR)
            from detect import score_sentences
            top_sents = score_sentences(text, top_n=5)
        except Exception:
            pass
        # 注入维度得分，让 LLM 知道哪些方面最需要改
        if hasattr(detect_result, 'dimension_scores') and detect_result.dimension_scores:
            top_dims = sorted(detect_result.dimension_scores.items(), key=lambda x: -x[1])[:5]
            dim_scores_hint = '\n'.join(f'  - {d}: {s}分' for d, s in top_dims)

    sys_prompt = build_system_prompt(mode, intensity, top_sents)
    # 在 prompt 末尾追加维度得分提示
    if dim_scores_hint:
        sys_prompt += f'\n\n## 当前文本最突出的 AI 特征维度（按严重程度排序）\n{dim_scores_hint}\n请重点针对以上维度进行改写。'

    if verbose:
        print(f'[rewrite] mode={mode} intensity={intensity} model={model}', file=sys.stderr)

    if dry_run:
        print('=' * 60 + '\nSYSTEM PROMPT:\n' + sys_prompt + '\n' + '=' * 60)
        print('USER TEXT:\n' + text + '\n' + '=' * 60)
        return {'rewritten': text, 'mode': mode, 'intensity': intensity,
                'model': model, 'error': None, 'dry_run': True}

    rewritten, err = call_with_retry(sys_prompt, text, model=model)
    if err:
        return {'rewritten': text, 'mode': mode, 'intensity': intensity,
                'model': model, 'error': err}

    rewritten = _clean_llm_output(rewritten)

    # 后处理：用本地替换词库做一轮零成本清理
    rewritten = apply_replacements(rewritten, mode=mode)

    return {'rewritten': rewritten, 'mode': mode, 'intensity': intensity,
            'model': model, 'error': None}

# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description='中文 AI 文本改写 v2.0 · 七牛云')
    parser.add_argument('file', nargs='?')
    parser.add_argument('--mode',    choices=['academic','general'], default='academic')
    parser.add_argument('--intensity', choices=['conservative','aggressive'])
    parser.add_argument('--model',   default=QN_MODEL)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-o', '--output')
    parser.add_argument('--with-detect', action='store_true')
    args = parser.parse_args()

    text = open(args.file, 'r', encoding='utf-8').read() if args.file else sys.stdin.read()
    if not text.strip():
        print('错误: 输入为空', file=sys.stderr); sys.exit(1)

    detect_result = None
    if args.with_detect:
        sys.path.insert(0, SCRIPT_DIR)
        from detect import detect as run_detect
        detect_result = run_detect(text)

    result = rewrite(text, mode=args.mode, intensity=args.intensity,
                     detect_result=detect_result, model=args.model,
                     dry_run=args.dry_run, verbose=args.verbose)
    if result.get('error'):
        print(f'[错误] {result["error"]}', file=sys.stderr); sys.exit(1)

    out = result['rewritten']
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已保存到: {args.output}')
    else:
        print(out)

if __name__ == '__main__':
    main()
