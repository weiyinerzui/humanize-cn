"""Integration tests for humanize.py Adversarial Beam v2.0 pipeline."""
import pytest
from unittest.mock import patch, MagicMock

from detect import DetectionResult


# ─── Helpers ─────────────────────────────────────────────────

def make_detect_result(score, issues=None, dims=None):
    """Create a DetectionResult with given score."""
    r = DetectionResult()
    r.final_score = score
    r.issues = issues or []
    r.dimension_scores = dims or {}
    r.stats = {
        'chars': 45, 'sentences': 2, 'avg_len': 22.5,
        'avg_sent_len': 22.5, 'burstiness': 0.3,
        'ngram_perplexity': None
    }
    return r


def make_report(text='...'):
    """Create a mock report dict."""
    return {'text_report': text, 'json_report': '{}', 'html_report': '<html></html>'}


# ─── Fixtures ────────────────────────────────────────────────

@pytest.fixture
def sample_text():
    return "人工智能技术的快速发展推动了数字化转型进程。值得注意的是，过度依赖技术可能导致系统性风险。"


@pytest.fixture
def detect_low():
    return make_detect_result(18, [
        {'category': '机械连接词', 'severity': 1, 'description': '...', 'snippet': '值得注意的是'}
    ])


@pytest.fixture
def detect_medium():
    return make_detect_result(45)


@pytest.fixture
def detect_high():
    return make_detect_result(75, [
        {'category': '句式单调', 'severity': 2},
        {'category': '空洞宏大词', 'severity': 3},
        {'category': '机械连接词', 'severity': 4},
    ])


@pytest.fixture
def detect_very_low():
    return make_detect_result(12)


@pytest.fixture
def beam_text():
    return 'AI技术飞速发展，带动了数字化进程。不过，如果过度依赖技术，也可能带来系统性风险。'


# ─── detect_only mode ────────────────────────────────────────

@patch('humanize.run_detect')
@patch('humanize.generate_report')
@patch('humanize.beam_rewrite')
def test_pipeline_detect_only(mock_beam, mock_report, mock_detect, sample_text, detect_low):
    """detect_only=True 时跳过所有改写，返回原文."""
    mock_detect.return_value = detect_low

    from humanize import pipeline
    result = pipeline(sample_text, detect_only=True)

    mock_beam.assert_not_called()
    mock_report.assert_not_called()
    assert result['rewritten'] == sample_text
    assert result['detect_before'].final_score == 18


# ─── Dry run mode ────────────────────────────────────────────

@patch('humanize.run_detect')
@patch('humanize.generate_report')
@patch('humanize.beam_rewrite')
@patch('humanize.polish')
def test_pipeline_dry_run(mock_polish, mock_beam, mock_report, mock_detect, sample_text, detect_low):
    """dry_run=True 时跳过 LLM + polish，改写文本=原文."""
    mock_detect.side_effect = [detect_low]

    from humanize import pipeline
    result = pipeline(sample_text, dry_run=True)

    mock_beam.assert_not_called()
    mock_polish.assert_not_called()
    assert result['rewritten'] == sample_text
    assert result['rewrite_result'] == {'dry_run': True}


# ─── Full pipeline ───────────────────────────────────────────

@patch('humanize.run_detect')
@patch('humanize.generate_report')
@patch('humanize.beam_rewrite')
@patch('humanize.polish')
def test_pipeline_full_flow(mock_polish, mock_beam, mock_report, mock_detect,
                             sample_text, detect_low, detect_very_low, beam_text):
    """完整五阶段流水线."""
    mock_detect.side_effect = [detect_low, detect_very_low]
    mock_beam.return_value = beam_text
    mock_polish.return_value = beam_text
    mock_report.return_value = make_report()

    from humanize import pipeline
    result = pipeline(sample_text, mode='academic', beam_k=3)

    # Phase 2: beam rewrite called
    mock_beam.assert_called_once_with(sample_text, mode='academic', k=3,
                                       model=None, verbose=False)
    # Phase 3: polish called
    mock_polish.assert_called_once()
    # Phase 4: detect called twice (before + after)
    assert mock_detect.call_count == 2
    # Phase 5: report called
    mock_report.assert_called_once()
    # Returns rewritten text
    assert result['rewritten'] == beam_text


# ─── No polish ───────────────────────────────────────────────

@patch('humanize.run_detect')
@patch('humanize.generate_report')
@patch('humanize.beam_rewrite')
@patch('humanize.polish')
def test_pipeline_no_polish(mock_polish, mock_beam, mock_report, mock_detect,
                             sample_text, detect_low, detect_very_low, beam_text):
    """polish_enabled=False 时跳过 L1 精修."""
    mock_detect.side_effect = [detect_low, detect_very_low]
    mock_beam.return_value = beam_text
    mock_report.return_value = make_report()

    from humanize import pipeline
    result = pipeline(sample_text, polish_enabled=False)

    mock_polish.assert_not_called()
    assert result['rewritten'] == beam_text


# ─── 高 AI 味 → 低 AI 味 score delta 验证 ───────────────────

@patch('humanize.run_detect')
@patch('humanize.generate_report')
@patch('humanize.beam_rewrite')
@patch('humanize.polish')
def test_pipeline_high_to_low_score(mock_polish, mock_beam, mock_report, mock_detect,
                                     sample_text, detect_high, detect_very_low, beam_text):
    """原文高分 → 改写低分的 score delta 验证."""
    mock_detect.side_effect = [detect_high, detect_very_low]
    mock_beam.return_value = beam_text
    mock_polish.return_value = beam_text
    mock_report.return_value = make_report()

    from humanize import pipeline
    result = pipeline(sample_text, mode='academic', beam_k=3)

    assert result['detect_before'].final_score == 75
    assert result['detect_after'].final_score == 12
    assert result['rewritten'] == beam_text


# ─── 输入文件路径 ────────────────────────────────────────────

@patch('humanize.run_detect')
@patch('humanize.generate_report')
@patch('humanize.beam_rewrite')
@patch('humanize.polish')
def test_pipeline_with_input_path(mock_polish, mock_beam, mock_report, mock_detect,
                                   sample_text, detect_medium, beam_text):
    """传入 input_path 时 report 包含 title."""
    mock_detect.return_value = detect_medium
    mock_beam.return_value = beam_text
    mock_polish.return_value = beam_text
    mock_report.return_value = make_report()

    from humanize import pipeline
    pipeline(sample_text, input_path='/tmp/test.docx')

    # report 被调用时 title 应为文件名
    call_kwargs = mock_report.call_args[1]
    assert call_kwargs['title'] == 'test.docx'


# ─── 参数传递验证 ────────────────────────────────────────────

@patch('humanize.run_detect')
@patch('humanize.generate_report')
@patch('humanize.beam_rewrite')
@patch('humanize.polish')
def test_pipeline_params_forward(mock_polish, mock_beam, mock_report, mock_detect,
                                  sample_text, detect_medium, beam_text):
    """验证 beam_k 和 model 参数正确传递."""
    mock_detect.return_value = detect_medium
    mock_beam.return_value = beam_text
    mock_polish.return_value = beam_text
    mock_report.return_value = make_report()

    from humanize import pipeline
    pipeline(sample_text, mode='informal', beam_k=5, model='qwen/qwen3', verbose=True)

    mock_beam.assert_called_once_with(
        sample_text, mode='informal', k=5,
        model='qwen/qwen3', verbose=True
    )