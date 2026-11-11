# Evaluation

Measures how well ForgeMind finds the right passages and writes good answers, so you can see whether a change
(a new manual, a different chunk size, semantic search on or off) made things better or worse.

```
evaluation/
├── benchmark.json     the questions and what a good answer must contain
├── run_benchmark.py   the scorer
├── README.md          this file
└── results/           saved runs (git-ignored; only .gitkeep is tracked)
```

## 1. Prepare

1. Upload your manuals (Upload page). The scorer reads the real index in `data/indexes`, so it needs documents.
2. Edit `benchmark.json` so the questions match **your** manuals:
   - `question`: what a technician would ask.
   - `expected_keywords`: words a correct answer must contain (the more specific, the better).
   - `expected_document`: the PDF file name that holds the answer. Leave `""` if you do not know it yet.
   - `category`: any label you like; use it to run part of the set with `--category`.

## 2. Run (from the project root)

```powershell
python -m evaluation.run_benchmark --retrieval-only      # free: no model calls
python -m evaluation.run_benchmark                       # also scores the written answers
python -m evaluation.run_benchmark --save                # keeps the run in evaluation/results/
python -m evaluation.run_benchmark --category safety -v  # one category, with details
python -m evaluation.run_benchmark --min-pass-rate 0.8   # exit code 1 if fewer than 80% pass
```

Other options: `--top-k` (1 to 10), `--threshold` (keyword share needed to pass, default 0.5), `--json FILE`.

## 3. Read the results

| Column | Meaning |
|---|---|
| Result | PASS when enough keywords were found and, if set, the expected document was retrieved |
| Doc | `#1` = expected document found at rank 1; `miss` = not in the top K; `-` = no expected document set |
| Retr. | share of expected keywords found in the retrieved passages |
| Answer | share of expected keywords found in the answer |
| Source of answer | the Gemini model name, `extractive` (excerpts; no key or model unavailable) or `none` (nothing found) |

Summary lines:
- **Document hit rate** and **MRR** (mean reciprocal rank: 1 for rank 1, 0.5 for rank 2, 0 for a miss) are about *retrieval*.
- **Citation rate** is how often a model-written answer cited its passages.

How to diagnose a FAIL:
- Retr. is low: the right text was not retrieved. Check the upload, the chunk size, or add keywords people really use.
- Retr. is high but Answer is low: retrieval worked, the answer missed the facts. Look at the prompt and the model.
- Doc says `miss`: the answer came from a different document than you expected.

Keyword scoring is a simple, repeatable check, not a judgement of meaning. Read a few answers yourself as well.

## Exit codes

`0` finished, `1` pass rate below `--min-pass-rate`, `2` setup problem (bad benchmark file, empty knowledge base).