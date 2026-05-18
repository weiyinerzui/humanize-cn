#!/usr/bin/env python3
"""
semantic_sim.py - Lightweight Semantic Similarity Metric
Uses Character Bi-gram TF-IDF Cosine Similarity for Chinese text.
"""
import re
import math
from collections import Counter

def _extract_chinese(text):
    return ''.join(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]+', text))

def get_bigrams(text):
    chars = _extract_chinese(text)
    if len(chars) < 2:
        return [chars] if chars else []
    return [chars[i:i+2] for i in range(len(chars)-1)]

import warnings
warnings.filterwarnings('ignore', category=UserWarning) # Suppress huggingface warnings

_SBERT_MODEL = None

def get_sbert_model():
    global _SBERT_MODEL
    if _SBERT_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            import os
            # Suppress symlink warning on windows
            os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
            _SBERT_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        except ImportError:
            _SBERT_MODEL = False # False means unavailable
    return _SBERT_MODEL

def compute_semantic_similarity(text1: str, text2: str) -> float:
    """
    Compute cosine similarity. Uses sentence-transformers (Option B) if available,
    otherwise falls back to Character Bi-gram TF-IDF.
    Returns a float between 0.0 and 1.0.
    """
    if not text1 or not text2:
        return 0.0
        
    model = get_sbert_model()
    if model:
        import torch
        from sentence_transformers import util
        embeddings1 = model.encode(text1, convert_to_tensor=True)
        embeddings2 = model.encode(text2, convert_to_tensor=True)
        cos_score = util.cos_sim(embeddings1, embeddings2).item()
        return round(max(0.0, cos_score), 4)

    # --- Fallback to Bigram TF-IDF ---
    bigrams1 = get_bigrams(text1)
    bigrams2 = get_bigrams(text2)
    
    if not bigrams1 or not bigrams2:
        return 1.0 if _extract_chinese(text1) == _extract_chinese(text2) else 0.0
        
    c1 = Counter(bigrams1)
    c2 = Counter(bigrams2)
    
    terms = set(c1.keys()).union(set(c2.keys()))
    
    dot_product = sum(c1.get(t, 0) * c2.get(t, 0) for t in terms)
    mag1 = math.sqrt(sum(v**2 for v in c1.values()))
    mag2 = math.sqrt(sum(v**2 for v in c2.values()))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
        
    return round(dot_product / (mag1 * mag2), 4)

if __name__ == '__main__':
    t1 = "M公司在制定混合股利支付政策时，需以法律法规及监管要求为基本前提"
    t2 = "M公司在设计混合股利支付政策时，必须先把法律法规和监管要求作为底线"
    print(f"Similarity: {compute_semantic_similarity(t1, t2)}")
