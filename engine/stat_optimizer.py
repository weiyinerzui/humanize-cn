#!/usr/bin/env python3
"""
stat_optimizer.py

Phase 2.5: 统计特征优化器
在 L3 Beam 改写与 L1 精修之间，对爆发度、困惑度等进行校正。
"""

import sys, os, random
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from text_utils import split_sentences, merge_sentences
from ngram_model import score_text

def optimize_burstiness(text: str) -> str:
    """如果爆发度不足，强行通过断句和连接增加波动"""
    sentences = split_sentences(text)
    if len(sentences) < 4:
        return text
    
    # 获取原始爆发度
    stats = score_text(text)
    burst = stats.get('burstiness', 0)
    
    if burst < 0.35:
        # 人为调整句长：找最长的切断
        lengths = [len(s) for s in sentences]
        max_idx = lengths.index(max(lengths))
        
        # 拆分最长句
        s_max = sentences[max_idx]
        if '，' in s_max[20:-20]:
            parts = s_max.split('，')
            mid = len(parts) // 2
            sentences[max_idx] = '，'.join(parts[:mid]) + '。进而，' + '，'.join(parts[mid:])
            
    return merge_sentences(sentences)

def optimize_perplexity(text: str) -> str:
    """如果困惑度过低，注入同义词替换"""
    # 暂时用简单的规则模拟罕见词替换以抬高困惑度
    replacements = {
        '因此': '鉴于此',
        '发现': '揭示出',
        '表明': '映射出',
        '基础': '基石',
        '方法': '进路',
        '问题': '症结',
        '结果': '指征'
    }
    stats = score_text(text)
    ppl = stats.get('perplexity', 1000)
    
    # 困惑度过低意味着像AI的平滑输出
    if ppl < 300:
        for k, v in replacements.items():
            if k in text:
                text = text.replace(k, v, 1)
                
    return text

def run_statistical_optimization(text: str) -> str:
    """运行统计特征优化闭环"""
    if not text or not text.strip():
        return text
    text = optimize_burstiness(text)
    text = optimize_perplexity(text)
    return text
