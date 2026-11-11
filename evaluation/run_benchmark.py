"""Score retrieval and answer quality against evaluation/benchmark.json.

It calls the same code the API uses (``retrieval.search`` then ``generate_answer``), in-process, so the
backend does not need to be running. It reads the real index in ``data/indexes``: upload your manuals first.

Run from the project root:

    python -m evaluation.run_benchmark                      # full run (uses Gemini when a key is set)
    python -m evaluation.run_benchmark --retrieval-only     # no model calls, nothing to pay for
    python -m evaluation.run_benchmark --save               # writes evaluation/results/run-<date-time>.json
    python -m evaluation.run_benchmark --top-k 6 --json my_run.json
    python -m evaluation.run_benchmark --category safety -v
    python -m evaluation.run_benchmark --min-pass-rate 0.8  # exit code 1 below 80% (for CI)

What is measured for every question
    retrieval  - does a passage from ``expected_document`` appear in the top K (hit and rank), and what share of
                 ``expected_keywords`` appear anywhere in the retrieved passages.
    answer     - what share of ``expected_keywords`` appear in the answer, and whether the model cited passages.
A question PASSES when its keyword share reaches ``--threshold`` and, if ``expected_document`` is set, that
document was retrieved. Without a Gemini key the "answer" is the extractive fallback, which is reported as such.

Exit codes: 0 ok, 1 pass rate below --min-pass-rate, 2 setup problem (bad file, empty knowledge base).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow `python evaluation/run_benchmark.py` as well as `-m`
    sys.path.insert(0, str(ROOT))

DEFAULT_BENCHMARK = Path(__file__).resolve().parent / "benchmark.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"  # git-ignored output folder
DEFAULT_THRESHOLD = 0.5


class BenchmarkError(ValueError):
    """The benchmark file or the environment is not usable."""


# ---- data -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Question:
    id: str
    question: str
    category: str = ""
    expected_document: str = ""
    expected_keywords: tuple[str, ...] = ()


@dataclass
class Result:
    id: str
    category: str
    question: str
    retrieved_documents: list[str] = field(default_factory=list)
    document_rank: int | None = None  # 1-based rank of the first passage from expected_document
    document_hit: bool | None = None  # None when the question names no expected document
    retrieval_keyword_recall: float | None = None
    answer_keyword_coverage: float | None = None
    missing_keywords: list[str] = field(default_factory=list)
    generated_by: str = ""
    cited: bool | None = None  # None unless a model wrote the answer
    retrieval_mode: str = ""
    latency_ms: int = 0
    passed: bool = False
    error: str = ""


def load_benchmark(path: Path) -> list[Question]:
    """Read and validate the benchmark file; raises BenchmarkError with a message fit to print."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BenchmarkError(f"Benchmark file not found: {path}") from None
    except (OSError, ValueError) as exc:
        raise BenchmarkError(f"Could not read {path}: {exc}") from None

    items = raw.get("questions") if isinstance(raw, dict) else None
    if not isinstance(items, list) or not items:
        raise BenchmarkError(f"{path.name} must contain a non-empty 'questions' list.")

    questions: list[Question] = []
    seen: set[str] = set()
    for position, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise BenchmarkError(f"Question #{position} must be an object.")
        qid = str(item.get("id") or f"q{position}")
        text = str(item.get("question") or "").strip()
        keywords = item.get("expected_keywords", [])
        if qid in seen:
            raise BenchmarkError(f"Duplicate question id: {qid}")
        if not text:
            raise BenchmarkError(f"Question {qid} has no text.")
        if not isinstance(keywords, list) or not all(isinstance(k, str) and k.strip() for k in keywords):
            raise BenchmarkError(f"Question {qid}: expected_keywords must be a list of non-empty strings.")
        seen.add(qid)
        questions.append(Question(
            id=qid, question=text, category=str(item.get("category") or ""),
            expected_document=str(item.get("expected_document") or "").strip(),
            expected_keywords=tuple(k.strip() for k in keywords),
        ))
    return questions


# ---- scoring (pure functions, unit-tested) ----------------------------------------------------
def normalize(text: str) -> str:
    """Lower-case and reduce punctuation to single spaces, so 'Lockout/Tagout' matches 'lockout tagout'."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.lower()).split())


def keyword_coverage(text: str, keywords: Sequence[str]) -> tuple[float | None, list[str]]:
    """(share of keywords found in text, the missing ones). None when there are no keywords to check."""
    if not keywords:
        return None, []
    haystack = f" {normalize(text)} "
    # A keyword matches from the start of a word, so "vibration" finds "vibrations" but "oil" does not find "boiler".
    missing = [k for k in keywords if f" {normalize(k)}" not in haystack]
    return (len(keywords) - len(missing)) / len(keywords), missing


def _doc_key(name: str) -> str:
    return normalize(Path(name).stem if name.lower().endswith(".pdf") else name)


def document_rank(passages: Sequence[dict], expected: str) -> int | None:
    """1-based position of the first passage whose document matches ``expected`` (file name, with or without .pdf)."""
    if not expected:
        return None
    want = _doc_key(expected)
    for position, passage in enumerate(passages, start=1):
        if _doc_key(str(passage.get("document", ""))) == want:
            return position
    return None


def judge(result: Result, threshold: float) -> bool:
    """Pass = enough keywords (answer if one was written, else retrieved text) and the expected document found."""
    if result.error:
        return False
    if result.document_hit is False:
        return False
    score = result.answer_keyword_coverage if result.answer_keyword_coverage is not None else result.retrieval_keyword_recall
    return True if score is None else score >= threshold


def summarize(results: Sequence[Result]) -> dict[str, Any]:
    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    scored_docs = [r for r in results if r.document_hit is not None]
    model_answers = [r for r in results if r.cited is not None]
    ranks = [(1 / r.document_rank) if r.document_rank else 0.0 for r in scored_docs]
    return {
        "questions": len(results),
        "passed": sum(r.passed for r in results),
        "pass_rate": round(sum(r.passed for r in results) / len(results), 3) if results else 0.0,
        "errors": sum(bool(r.error) for r in results),
        "document_hit_rate": mean([1.0 if r.document_hit else 0.0 for r in scored_docs]),
        "mean_reciprocal_rank": mean(ranks),
        "retrieval_keyword_recall": mean([r.retrieval_keyword_recall for r in results if r.retrieval_keyword_recall is not None]),
        "answer_keyword_coverage": mean([r.answer_keyword_coverage for r in results if r.answer_keyword_coverage is not None]),
        "citation_rate": mean([1.0 if r.cited else 0.0 for r in model_answers]),
        "mean_latency_ms": mean([float(r.latency_ms) for r in results]),
    }


# ---- running ----------------------------------------------------------------------------------
def evaluate(question: Question, top_k: int, retrieval_only: bool, threshold: float) -> Result:
    from backend.app.generation.gemini_client import generate_answer
    from backend.app.retrieval import search as retrieval

    result = Result(id=question.id, category=question.category, question=question.question)
    started = time.perf_counter()
    try:
        passages, mode = retrieval.search(question.question, top_k)
        result.retrieval_mode = mode
        result.retrieved_documents = list(dict.fromkeys(str(p["document"]) for p in passages))

        rank = document_rank(passages, question.expected_document)
        if question.expected_document:
            result.document_rank, result.document_hit = rank, rank is not None

        retrieved_text = " ".join(str(p["text"]) for p in passages)
        result.retrieval_keyword_recall, retrieved_missing = keyword_coverage(retrieved_text, question.expected_keywords)
        result.missing_keywords = retrieved_missing

        if not retrieval_only:
            generated = generate_answer(question.question, passages)
            result.generated_by = generated.generated_by
            result.answer_keyword_coverage, result.missing_keywords = keyword_coverage(generated.answer, question.expected_keywords)
            if generated.generated_by not in ("extractive", "none"):
                result.cited = bool(generated.cited)
    except Exception as exc:  # one bad question must not hide the rest
        result.error = f"{type(exc).__name__}: {exc}"
    result.latency_ms = int((time.perf_counter() - started) * 1000)
    result.passed = judge(result, threshold)
    return result


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def print_report(results: Sequence[Result], summary: dict[str, Any], top_k: int, retrieval_only: bool, verbose: bool) -> None:
    print(f"\nBenchmark: {summary['questions']} questions, top {top_k} passages each\n")
    print(f"{'ID':<5} {'Category':<16} {'Result':<6} {'Doc':<5} {'Retr.':>6} {'Answer':>7} {'ms':>6}  Source of answer")
    print("-" * 78)
    for r in results:
        doc = "-" if r.document_hit is None else (f"#{r.document_rank}" if r.document_hit else "miss")
        answer = "-" if retrieval_only else _pct(r.answer_keyword_coverage)
        origin = r.error or ("retrieval only" if retrieval_only else r.generated_by or "-")
        print(f"{r.id:<5} {r.category[:16]:<16} {'PASS' if r.passed else 'FAIL':<6} {doc:<5} "
              f"{_pct(r.retrieval_keyword_recall):>6} {answer:>7} {r.latency_ms:>6}  {origin}")
        if verbose or not r.passed:
            if r.missing_keywords:
                print(f"      missing keywords: {', '.join(r.missing_keywords)}")
            if verbose:
                print(f"      question: {r.question}\n      documents: {', '.join(r.retrieved_documents) or 'none'}")
    print("-" * 78)
    print(f"Passed {summary['passed']} of {summary['questions']} ({_pct(summary['pass_rate'])})")
    print(f"Document hit rate: {_pct(summary['document_hit_rate'])}   MRR: {summary['mean_reciprocal_rank'] if summary['mean_reciprocal_rank'] is not None else 'n/a'}")
    print(f"Keywords found in retrieved passages: {_pct(summary['retrieval_keyword_recall'])}")
    if not retrieval_only:
        print(f"Keywords found in answers: {_pct(summary['answer_keyword_coverage'])}   Citation rate (model answers): {_pct(summary['citation_rate'])}")
        if any(r.generated_by == "extractive" for r in results):
            print("Note: some answers are the extractive fallback (no Gemini key or the model was unavailable), not model-written text.")
    if summary["document_hit_rate"] is None:
        print("Note: no question sets expected_document, so document hit rate and MRR are not measured.")
    print()


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evaluation.run_benchmark", description=__doc__.split("\n\n")[0])
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK, help="benchmark JSON file")
    parser.add_argument("--top-k", type=int, default=None, help="passages to retrieve (default: the app's TOP_K setting)")
    parser.add_argument("--retrieval-only", action="store_true", help="skip answer generation (no model calls)")
    parser.add_argument("--category", help="only questions in this category")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="keyword share needed to pass (0 to 1)")
    parser.add_argument("--min-pass-rate", type=float, default=None, help="exit with code 1 if the pass rate is lower (0 to 1)")
    parser.add_argument("--json", type=Path, dest="json_out", help="also write the full results to this file")
    parser.add_argument("--save", action="store_true", help="write the results to evaluation/results/run-<date-time>.json")
    parser.add_argument("-v", "--verbose", action="store_true", help="show details for passing questions too")
    args = parser.parse_args(argv)
    for name in ("threshold", "min_pass_rate"):
        value = getattr(args, name)
        if value is not None and not 0 <= value <= 1:
            parser.error(f"--{name.replace('_', '-')} must be between 0 and 1")
    if args.top_k is not None and not 1 <= args.top_k <= 10:
        parser.error("--top-k must be between 1 and 10")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        questions = load_benchmark(args.benchmark)
        if args.category:
            questions = [q for q in questions if q.category == args.category]
            if not questions:
                raise BenchmarkError(f"No questions in category {args.category!r}.")

        from backend.app.core.config import settings
        from backend.app.core.logging import configure_logging
        from backend.app.retrieval import vector_store

        configure_logging("WARNING", "text")  # keep the report readable
        if not vector_store.load_chunks():
            raise BenchmarkError("The knowledge base is empty. Upload your manuals first (Upload page or POST /api/documents/upload).")
    except BenchmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    top_k = args.top_k or settings.top_k
    results = [evaluate(q, top_k, args.retrieval_only, args.threshold) for q in questions]
    summary = summarize(results)
    print_report(results, summary, top_k, args.retrieval_only, args.verbose)

    targets = [args.json_out] if args.json_out else []
    if args.save:
        targets.append(RESULTS_DIR / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"summary": summary, "results": [asdict(r) for r in results]}, indent=2), encoding="utf-8")
        print(f"Results written to {target}")

    if args.min_pass_rate is not None and summary["pass_rate"] < args.min_pass_rate:
        print(f"Pass rate {_pct(summary['pass_rate'])} is below the required {_pct(args.min_pass_rate)}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())