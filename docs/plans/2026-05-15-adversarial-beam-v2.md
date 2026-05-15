# humanize-cn v2.0 "Adversarial Beam" Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Upgrade humanize-cn from L1 (single-pass prompt rewrite) to L3 adversarial beam search + L1 polish pipeline, achieving detectable AIGC score reduction on par with NeurIPS 2025 Adversarial Paraphrasing.

**Architecture:** 5-phase pipeline: detect baseline → beam search rewrite (sentence-level, K candidates scored by detect.py) → L1 rule-based polish → final detect → report. Uses QnAIGC API (OpenAI-compatible) as LLM backend.

**Tech Stack:** Python 3.12, pymupdf, pytest, QnAIGC API (deepseek/deepseek-v4-pro)

---

## Phase 0: Environment Setup & Validation

### Task 0.1: Fix .env with real API credentials

**Objective:** Replace placeholder API key with real QnAIGC credentials.

**Files:** Modify `.env`

**Step 1: Write real credentials**

```bash
QN_API_KEY=sk-611e29a7988c4aada1e4e6fa81939582
QN_MODEL=deepseek/deepseek-v4-pro
QN_BASE_URL=https://api.qnaigc.com/v1
```

**Step 2: Verify API connectivity**

```bash
cd /mnt/e/workspace/github/humanize-cn
python3 -c "
import os
os.environ['QN_API_KEY']='sk-611e29a7988c4aada1e4e6fa81939582'
os.environ['QN_BASE_URL']='https://api.qnaigc.com/v1'
os.environ['QN_MODEL']='deepseek/deepseek-v4-pro'
import rewrite
text, err = rewrite.call_llm('You are a rephraser.', 'Test: rewrite this.', max_tokens=50)
print('OK' if text else f'FAIL: {err}')
"
```

**Expected:** Prints "OK" with rewritten text.

### Task 0.2: Fix rewrite.py env var names

**Objective:** Fix truncated line 22 (`QN_API_KEY=os.env...EY`, '')`).

**Files:** Modify `rewrite.py:22`

**Step 1: Patch line 22**

Replace the truncated line with:
```python
QN_API_KEY = os.environ.get('QN_API_KEY', '') or os.environ.get('QNAIGC_API_TOKEN', '')
```

**Step 2: Verify**

```bash
cd /mnt/e/workspace/github/humanize-cn
python3 -c "import rewrite; print('MODEL:', rewrite.QN_MODEL); print('HAS_KEY:', bool(rewrite.QN_API_KEY))"
```

**Expected:** MODEL=deepseek/deepseek-v4-pro, HAS_KEY=True

---

## Phase 1: L3 Adversarial Beam Search Engine

### Task 1.1: Create text segmentation utilities

**Objective:** Split/merge Chinese text into sentences for beam search processing.

**Files:**
- Create: `text_utils.py`
- Create: `tests/test_text_utils.py`

**Step 1: Write tests first (TDD)**

File: `tests/test_text_utils.py`
```python
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from text_utils import split_sentences, merge_sentences

def test_split_chinese_sentences():
    text = "这是第一句。这是第二句！这是第三句？"
    result = split_sentences(text)
    assert len(result) == 3

def test_split_preserves_paragraphs():
    text = "段落1句A。段落1句B。\n\n段落2句A。"
    result = split_sentences(text)
    assert len(result) >= 3

def test_merge_roundtrip():
    text = "句子1。句子2。句子3。"
    parts = split_sentences(text)
    merged = merge_sentences(parts)
    assert merged == text

def test_split_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []

def test_split_mixed_en_zh():
    text = "This is a test. 中文句子。Another one."
    result = split_sentences(text)
    assert len(result) >= 3
```

**Step 2: Run tests → expect FAIL**

```bash
cd /mnt/e/workspace/github/humanize-cn
python3 -m pytest tests/test_text_utils.py -v
```

**Step 3: Implement text_utils.py**

```python
#!/usr/bin/env python3
"""Text segmentation utilities for Chinese text beam search."""

import re

_SENT_SPLIT = re.compile(r'([。！？；!?;\n]+)')

def split_sentences(text: str, min_len: int = 4) -> list[str]:
    """Split text into sentences, preserving terminators."""
    if not text or not text.strip():
        return []
    raw = _SENT_SPLIT.split(text)
    sentences = []
    buf = ""
    for part in raw:
        if not part:
            continue
        buf += part
        if _SENT_SPLIT.match(part):
            sentences.append(buf)
            buf = ""
    if buf.strip():
        sentences.append(buf)
    merged = []
    for s in sentences:
        if merged and len(s.strip()) < min_len:
            merged[-1] += s
        else:
            merged.append(s)
    return merged

def merge_sentences(sentences: list[str]) -> str:
    """Merge sentences back, preserving spacing."""
    return ''.join(sentences)
```

**Step 4: Run tests → expect PASS**

```bash
python3 -m pytest tests/test_text_utils.py -v
```

**Step 5: Commit**

```bash
git add text_utils.py tests/test_text_utils.py
git commit -m "feat: add text segmentation utilities for beam search"
```

### Task 1.2: Create beam search rewrite engine

**Objective:** Implement sentence-level beam search: for each sentence, generate K candidates via LLM, score each with detect.py, select lowest-score candidate.

**Files:**
- Create: `rewrite_beam.py`
- Create: `tests/test_rewrite_beam.py`

**Step 1: Write tests**

File: `tests/test_rewrite_beam.py`
```python
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from unittest.mock import patch, MagicMock

def test_generate_candidates_returns_k():
    from rewrite_beam import generate_candidates
    with patch('rewrite_beam.call_with_retry') as mock:
        mock.side_effect = [("改写结果" + str(i), None) for i in range(3)]
        candidates = generate_candidates("原文句子。", mode='general', k=3)
        assert len(candidates) == 3

def test_generate_candidates_fallback():
    from rewrite_beam import generate_candidates
    with patch('rewrite_beam.call_with_retry') as mock:
        mock.return_value = (None, "API error")
        candidates = generate_candidates("原文句子。", mode='academic', k=2)
        assert len(candidates) == 2
        # Should fall back to original text
        assert all(isinstance(c, str) for c in candidates)

def test_select_best_lowest_score():
    from rewrite_beam import select_best
    candidates = ["A_改写", "B_改写", "C_改写"]
    scores = [80, 25, 65]
    best = select_best(candidates, scores)
    assert best == "B_改写"

def test_beam_rewrite_empty():
    from rewrite_beam import beam_rewrite
    result = beam_rewrite("", mode='academic')
    assert result == ""

def test_beam_rewrite_short_text():
    from rewrite_beam import beam_rewrite
    with patch('rewrite_beam.beam_rewrite_sentence') as mock:
        mock.return_value = ["改写后文本。"]
        result = beam_rewrite("短文本。", mode='general', k=2, verbose=False)
        assert isinstance(result, str)
        assert len(result) > 0
```

**Step 2: Run tests → expect FAIL**

**Step 3: Implement rewrite_beam.py**

Full implementation includes:
- `generate_candidates(sentence, mode, k, model)` — calls LLM with K different prompt variants
- `select_best(candidates, scores)` — picks lowest detect score
- `score_candidates(candidates)` — calls detect.py on each candidate
- `beam_rewrite_sentence(sentence, mode, k, model)` — full beam cycle for one sentence
- `beam_rewrite(text, mode, k, model, verbose)` — orchestrates full beam pipeline
- CLI with argparse

Three prompt variants per mode (academic/general) for candidate diversity:
1. Standard rewrite prompt
2. Structure-variation prompt
3. Concise/condensed prompt

**Key design decisions:**
- Skip sentences shorter than 4 chars (noise/terminators)
- LLM errors fall back to original sentence
- detect.py errors assign worst score (100)
- Uses `call_with_retry` from rewrite.py (3 retries, 5s delay)

**Step 4: Run tests → expect PASS**

**Step 5: Commit**

---

## Phase 2: L1 Polish Engine

### Task 2.1: Create rule-based polish module

**Objective:** Post-process beam-rewritten text to clean residual AI patterns that beam search missed. Pure rules, no LLM calls.

**Files:**
- Create: `rewrite_polish.py`
- Create: `tests/test_rewrite_polish.py`

**Step 1: Write tests**

File: `tests/test_rewrite_polish.py`
```python
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rewrite_polish import polish, replace_mechanical_connectors

def test_replace_connectors_removes_ai_tells():
    text = "值得注意的是，AI发展迅速。综上所述，需要关注。"
    result = replace_mechanical_connectors(text)
    assert "值得注意的是" not in result
    assert "综上所述" not in result

def test_polish_returns_string():
    result = polish("这是测试文本。", mode='academic')
    assert isinstance(result, str)
    assert len(result) > 0

def test_polish_empty():
    assert polish("") == ""
    assert polish("  ") == ""

def test_polish_academic_preserves_terms():
    text = "量子计算推动了密码学进步。"
    result = polish(text, mode='academic')
    assert "量子计算" in result
    assert "密码学" in result

def test_polish_cleans_double_spaces():
    text = "句子  多余空格  。  继续。"
    result = polish(text, mode='general')
    assert "  " not in result
```

**Step 2: Run tests → expect FAIL**

**Step 3: Implement rewrite_polish.py**

Includes:
- `replace_mechanical_connectors(text)` — replaces 13 AI-typical connectors with natural alternatives
- `remove_filler_phrases(text)` — regex-based removal of filler patterns
- `vary_sentence_lengths(text)` — merges 30% of consecutive short sentences for burstiness
- `polish(text, mode)` — main entry point, chains all transformations

**Step 4: Run tests → expect PASS**

**Step 5: Commit**

---

## Phase 3: Integration — Update humanize.py Pipeline

### Task 3.1: Update pipeline to 5-phase flow

**Objective:** Modify `humanize.py` to use the new beam + polish pipeline.

**Files:** Modify `humanize.py`

**Changes:**
1. Import `beam_rewrite` from `rewrite_beam` and `polish` from `rewrite_polish`
2. Update `pipeline()` to 5 phases:
   - Phase 1: Detect baseline (unchanged)
   - Phase 2: L3 beam search rewrite
   - Phase 3: L1 rule-based polish
   - Phase 4: Final detect
   - Phase 5: Report generation
3. Add CLI args: `--beam-k` (default 3), `--no-polish` (flag)
4. Phase 2 replaces the old `run_rewrite()` call
5. Dry-run mode shows what would be called without API

**Step 1: Write integration test**

File: `tests/test_integration_v2.py`
```python
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

SAMPLE = "人工智能技术推动了数字化转型。值得注意的是，过度依赖技术可能导致风险。"

def test_pipeline_v2_structure():
    """Test that pipeline returns expected dict keys."""
    from humanize import pipeline
    result = pipeline(SAMPLE, dry_run=True)
    assert 'original' in result
    assert 'rewritten' in result
    assert 'detect_before' in result
```

**Step 2: Run → expect FAIL (new imports not yet in humanize.py)**

**Step 3: Implement updated humanize.py**

```python
# New imports
from rewrite_beam import beam_rewrite
from rewrite_polish import polish
```

**Step 4: Run all new tests → expect PASS**

```bash
python3 -m pytest tests/ -v --tb=short
```

**Step 5: Commit**

---

## Phase 4: Full Test Suite Validation

### Task 4.1: Run complete test suite

**Command:**
```bash
cd /mnt/e/workspace/github/humanize-cn
python3 -m pytest tests/ -v --tb=short 2>&1
```

**Expected:** All tests pass (old + new), 0 failures.

### Task 4.2: Live API smoke test

**Command:**
```bash
cd /mnt/e/workspace/github/humanize-cn
python3 humanize.py test.txt --mode academic --beam-k 2 --no-polish -v 2>&1 | head -50
```

**Expected:** Phases 1-5 all show output, no API errors.

---

## Phase 5: Human Testing & Calibration (Manual)

### Task 5.1: User submits real AI text for validation

**Process:**
1. User provides 1-3 real AI-generated Chinese text samples
2. Run: `python3 humanize.py sample.txt --mode academic --beam-k 3 -v`
3. User submits `sample_rewritten.txt` to 朱雀/维普/万方/知网
4. Compare detect.py scores vs real AIGC platform scores
5. Calibrate detect.py thresholds if correlation is weak

---

## File Manifest

| File | Status | Purpose |
|------|--------|---------|
| `text_utils.py` | NEW | Sentence splitting/merging |
| `rewrite_beam.py` | NEW | L3 beam search rewrite engine |
| `rewrite_polish.py` | NEW | L1 rule-based polish engine |
| `humanize.py` | MODIFIED | 5-phase pipeline integration |
| `rewrite.py` | MODIFIED | Fix .env var names (line 22) |
| `.env` | MODIFIED | Real QnAIGC credentials |
| `tests/test_text_utils.py` | NEW | 5 tests for text utils |
| `tests/test_rewrite_beam.py` | NEW | 5 tests for beam engine |
| `tests/test_rewrite_polish.py` | NEW | 5 tests for polish engine |
| `tests/test_integration_v2.py` | NEW | Integration tests for v2 pipeline |

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| QnAIGC API rate limiting with K*N calls | High | `call_with_retry` backoff; reduce `--beam-k` to 2 |
| Beam search latency (K * N_sentences) | Medium | Batch sentences or use paragraph-level beam |
| detect.py scores don't correlate with real detectors | High | Phase 5 calibration with real platform scores |
| Over-polishing causes semantic drift (academic) | Low | Academic polish is minimal (connectors only) |
| .env API key rejected | High | Phase 0 validation catches this early |

---

## Summary

This plan upgrades humanize-cn from a single-pass L1 prompt-based rewrite to a NeurIPS 2025-inspired adversarial beam search pipeline:

```
Input → detect → beam_search(K candidates, scored by detect.py) → polish → detect → report
```

The beam search approach is the key innovation: using our own detect.py as a "guidance detector" to select the most human-like candidate from K LLM-generated rewrites per sentence. This mirrors the Adversarial Paraphrasing paper's approach but adapted for API-based LLMs (sentence-level beam instead of token-level).

Total new code: ~400 lines across 3 new modules + modified humanize.py.
Total new tests: ~15 covering all new functionality.
