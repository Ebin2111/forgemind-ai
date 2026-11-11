"""Tests for the benchmark scorer (evaluation/run_benchmark.py): file validation and scoring rules."""
import json

import pytest

from evaluation import run_benchmark as rb


def _write(tmp_path, payload):
    path = tmp_path / "b.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_shipped_benchmark_file_is_valid():
    questions = rb.load_benchmark(rb.DEFAULT_BENCHMARK)
    assert len(questions) >= 1
    assert len({q.id for q in questions}) == len(questions)
    assert all(q.question and q.expected_keywords for q in questions)


@pytest.mark.parametrize("payload", [
    [],
    {"questions": []},
    {"questions": ["not an object"]},
    {"questions": [{"id": "a", "question": "  "}]},
    {"questions": [{"id": "a", "question": "x?", "expected_keywords": "oil"}]},
    {"questions": [{"id": "a", "question": "x?"}, {"id": "a", "question": "y?"}]},
])
def test_invalid_benchmark_files_are_rejected(tmp_path, payload):
    with pytest.raises(rb.BenchmarkError):
        rb.load_benchmark(_write(tmp_path, payload))


def test_missing_and_malformed_files(tmp_path):
    with pytest.raises(rb.BenchmarkError, match="not found"):
        rb.load_benchmark(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(rb.BenchmarkError, match="Could not read"):
        rb.load_benchmark(bad)


def test_missing_ids_are_numbered_and_blank_expected_document_is_allowed(tmp_path):
    q = rb.load_benchmark(_write(tmp_path, {"questions": [{"question": "How?", "expected_keywords": ["a"]}]}))[0]
    assert q.id == "q1" and q.expected_document == ""


def test_keyword_coverage_ignores_case_and_punctuation():
    cov, missing = rb.keyword_coverage("Apply Lockout/Tagout, then VERIFY zero energy.", ["lockout tagout", "verify", "isolate"])
    assert cov == pytest.approx(2 / 3) and missing == ["isolate"]


def test_keyword_matches_word_starts_only():
    assert rb.keyword_coverage("Check vibrations", ["vibration"])[0] == 1.0  # plural still matches
    assert rb.keyword_coverage("The boiler", ["oil"])[0] == 0.0  # no match inside another word


def test_keyword_coverage_without_keywords_is_not_measured():
    assert rb.keyword_coverage("anything", []) == (None, [])


@pytest.mark.parametrize("expected", ["pump_manual.pdf", "Pump_Manual", "pump manual"])
def test_document_rank_matches_name_loosely(expected):
    passages = [{"document": "other.pdf"}, {"document": "pump_manual.pdf"}]
    assert rb.document_rank(passages, expected) == 2


def test_document_rank_none_when_absent_or_not_expected():
    assert rb.document_rank([{"document": "a.pdf"}], "b.pdf") is None
    assert rb.document_rank([{"document": "a.pdf"}], "") is None


def _result(**kw):
    return rb.Result(id="q", category="c", question="?", **kw)


def test_judge_rules():
    assert rb.judge(_result(answer_keyword_coverage=0.5), 0.5)
    assert not rb.judge(_result(answer_keyword_coverage=0.4), 0.5)
    assert not rb.judge(_result(answer_keyword_coverage=1.0, document_hit=False), 0.5)  # right words, wrong document
    assert rb.judge(_result(retrieval_keyword_recall=0.9), 0.5)  # retrieval-only runs score the passages
    assert not rb.judge(_result(error="Boom", answer_keyword_coverage=1.0), 0.5)
    assert rb.judge(_result(), 0.5)  # nothing to measure is not a failure


def test_summarize_computes_rates():
    results = [
        _result(passed=True, document_hit=True, document_rank=1, answer_keyword_coverage=1.0, retrieval_keyword_recall=1.0, cited=True, latency_ms=10),
        _result(passed=False, document_hit=True, document_rank=2, answer_keyword_coverage=0.0, retrieval_keyword_recall=0.5, cited=False, latency_ms=30),
        _result(passed=False, document_hit=False, answer_keyword_coverage=0.5, retrieval_keyword_recall=0.0, latency_ms=20, error="x"),
    ]
    s = rb.summarize(results)
    assert s["pass_rate"] == pytest.approx(0.333, abs=1e-3) and s["errors"] == 1
    assert s["document_hit_rate"] == pytest.approx(0.667, abs=1e-3)
    assert s["mean_reciprocal_rank"] == pytest.approx(0.5)  # (1 + 1/2 + 0) / 3
    assert s["citation_rate"] == 0.5 and s["mean_latency_ms"] == 20.0


def test_summarize_handles_nothing_measured():
    s = rb.summarize([_result(passed=True)])
    assert s["document_hit_rate"] is None and s["citation_rate"] is None and s["answer_keyword_coverage"] is None


def test_main_reports_empty_knowledge_base(capsys):
    assert rb.main(["--retrieval-only"]) == 2  # the test data folders hold no documents
    assert "knowledge base is empty" in capsys.readouterr().err


@pytest.mark.parametrize("args", [["--top-k", "0"], ["--threshold", "2"], ["--min-pass-rate", "-1"]])
def test_bad_options_exit_with_usage_error(args):
    with pytest.raises(SystemExit) as exc:
        rb.parse_args(args)
    assert exc.value.code == 2