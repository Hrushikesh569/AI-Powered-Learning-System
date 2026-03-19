import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Allow running this script from repo root: `python backend/tools/evaluate_extraction.py ...`
THIS_FILE = Path(__file__).resolve()
BACKEND_DIR = THIS_FILE.parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def normalize_topic(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


@dataclass
class MetricResult:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    jaccard: float
    exact_match_ratio: float


def compute_set_metrics(expected: list[str], predicted: list[str]) -> MetricResult:
    exp = set(expected)
    pred = set(predicted)

    tp = len(exp & pred)
    fp = len(pred - exp)
    fn = len(exp - pred)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    union = len(exp | pred)
    jaccard = tp / union if union else 0.0

    exact_match_ratio = 1.0 if exp == pred else 0.0

    return MetricResult(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        jaccard=jaccard,
        exact_match_ratio=exact_match_ratio,
    )


async def extract_topics_from_file(file_path: str, hint_subject: str = "") -> list[str]:
    from app.core.syllabus_processing import extract_text_from_file
    from app.core.syllabus_intelligence import analyze_full_syllabus_document

    text = extract_text_from_file(file_path)
    analyses = await analyze_full_syllabus_document(text, hint_subject=hint_subject)

    topics = []
    for analysis in analyses:
        for unit in analysis.get("units", []):
            for t in unit.get("topics", []):
                name = t.get("name") if isinstance(t, dict) else str(t)
                name = normalize_topic(name)
                if name:
                    topics.append(name)

    return dedupe_keep_order(topics)


def load_gold(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Gold file must be a JSON array")
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            raise ValueError(f"Row {i} must be an object")
        if "file_path" not in row or "expected_topics" not in row:
            raise ValueError(f"Row {i} must include 'file_path' and 'expected_topics'")
    return data


async def run_eval(gold_rows: list[dict[str, Any]], workspace_root: Path) -> dict[str, Any]:
    per_file = []

    tp_sum = fp_sum = fn_sum = 0
    exact_sum = 0.0

    for row in gold_rows:
        rel = row["file_path"]
        full_path = (workspace_root / rel).resolve()
        hint_subject = row.get("subject", "")
        expected_raw = row.get("expected_topics", [])

        expected = dedupe_keep_order([normalize_topic(x) for x in expected_raw if normalize_topic(str(x))])

        predicted = await extract_topics_from_file(str(full_path), hint_subject=hint_subject)

        m = compute_set_metrics(expected, predicted)
        tp_sum += m.tp
        fp_sum += m.fp
        fn_sum += m.fn
        exact_sum += m.exact_match_ratio

        per_file.append({
            "file_path": rel,
            "expected_count": len(expected),
            "predicted_count": len(predicted),
            "tp": m.tp,
            "fp": m.fp,
            "fn": m.fn,
            "precision": round(m.precision, 4),
            "recall": round(m.recall, 4),
            "f1": round(m.f1, 4),
            "jaccard": round(m.jaccard, 4),
            "exact_match": round(m.exact_match_ratio, 4),
        })

    micro_precision = tp_sum / (tp_sum + fp_sum) if (tp_sum + fp_sum) else 0.0
    micro_recall = tp_sum / (tp_sum + fn_sum) if (tp_sum + fn_sum) else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if (micro_precision + micro_recall)
        else 0.0
    )
    micro_jaccard = tp_sum / (tp_sum + fp_sum + fn_sum) if (tp_sum + fp_sum + fn_sum) else 0.0

    macro_precision = sum(r["precision"] for r in per_file) / len(per_file) if per_file else 0.0
    macro_recall = sum(r["recall"] for r in per_file) / len(per_file) if per_file else 0.0
    macro_f1 = sum(r["f1"] for r in per_file) / len(per_file) if per_file else 0.0
    macro_jaccard = sum(r["jaccard"] for r in per_file) / len(per_file) if per_file else 0.0
    exact_match_rate = exact_sum / len(per_file) if per_file else 0.0

    return {
        "summary": {
            "files": len(per_file),
            "micro_precision": round(micro_precision, 4),
            "micro_recall": round(micro_recall, 4),
            "micro_f1": round(micro_f1, 4),
            "micro_jaccard": round(micro_jaccard, 4),
            "macro_precision": round(macro_precision, 4),
            "macro_recall": round(macro_recall, 4),
            "macro_f1": round(macro_f1, 4),
            "macro_jaccard": round(macro_jaccard, 4),
            "exact_match_rate": round(exact_match_rate, 4),
            "tp_total": tp_sum,
            "fp_total": fp_sum,
            "fn_total": fn_sum,
        },
        "per_file": per_file,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate syllabus topic extraction accuracy against gold labels"
    )
    parser.add_argument("--gold", required=True, help="Path to gold JSON file")
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root to resolve file_path values in gold file",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional path to write JSON results",
    )

    args = parser.parse_args()

    workspace_root = Path(args.workspace).resolve()
    gold_rows = load_gold(Path(args.gold).resolve())
    results = asyncio.run(run_eval(gold_rows, workspace_root))

    print(json.dumps(results["summary"], indent=2))

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Saved detailed report: {args.out}")


if __name__ == "__main__":
    main()
