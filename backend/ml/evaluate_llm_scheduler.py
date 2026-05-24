"""Evaluate the live LLM-guided scheduler with operational metrics.

This script replaces the old supervised reschedule benchmark with metrics that
describe the current planner behavior:
- whether the LLM was actually used
- how many topics were guided or forced forward
- how much of the curriculum was scheduled within the evaluation window
- how early missed / skipped topics were front-loaded
- how the resulting schedule is distributed across days

Run from the backend directory:
    python ml/evaluate_llm_scheduler.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core.syllabus_intelligence import generate_llm_adaptive_schedule


DB_PATH = os.path.join(ROOT, "ai_learning.db")
OUT_DIR = os.path.join(ROOT, "app", "evaluation_plots", "summary")
METRICS_PATH = os.path.join(OUT_DIR, "llm_scheduler_metrics.json")
SUMMARY_PLOT = os.path.join(OUT_DIR, "llm_scheduler_summary.png")
TIMELINE_PLOT = os.path.join(OUT_DIR, "llm_scheduler_timeline.png")


def _ensure_out_dir() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)


def _load_topics() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT subject, subject_code, unit_name, unit_index, topic_name, topic_index,
               estimated_hours, difficulty, status, material_id
        FROM scheduled_topics
        ORDER BY subject, unit_index, topic_index, id
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _difficulty_to_num(value: str | None) -> int:
    mapping = {
        "easy": 1,
        "basic": 2,
        "intermediate": 3,
        "medium": 3,
        "hard": 4,
        "advanced": 5,
    }
    if value is None:
        return 3
    text = str(value).strip().lower()
    if text.isdigit():
        return max(1, min(5, int(text)))
    return mapping.get(text, 3)


def _build_analyses(rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        subject = row.get("subject") or "Unknown"
        subject_entry = grouped.setdefault(
            subject,
            {
                "subject_name": subject,
                "subject_code": row.get("subject_code") or "",
                "overview": "",
                "units": {},
            },
        )
        if not subject_entry.get("subject_code"):
            subject_entry["subject_code"] = row.get("subject_code") or ""

        unit_key = row.get("unit_name") or "Unit"
        units = subject_entry["units"]
        unit_entry = units.setdefault(
            unit_key,
            {
                "unit_name": unit_key,
                "unit_number": int(row.get("unit_index") or 0) + 1,
                "topics": [],
                "_idx": int(row.get("unit_index") or 0),
            },
        )

        difficulty = _difficulty_to_num(row.get("difficulty"))
        unit_entry["topics"].append(
            {
                "name": row.get("topic_name") or "",
                "difficulty": difficulty,
                "est_hours": float(row.get("estimated_hours") or 1.0),
                "prerequisites": [],
                "key_concepts": [],
                "is_foundational": difficulty <= 2,
                "status": row.get("status") or "pending",
            }
        )

    analyses = []
    for subject in sorted(grouped.keys()):
        entry = grouped[subject]
        unit_list = sorted(entry["units"].values(), key=lambda unit: unit.get("_idx", 0))
        for unit in unit_list:
            unit.pop("_idx", None)
            unit["topics"].sort(key=lambda topic: (topic.get("status") != "completed", topic.get("difficulty", 3), topic.get("name", "")))
        analyses.append(
            {
                "subject_name": entry["subject_name"],
                "subject_code": entry.get("subject_code", ""),
                "overview": entry.get("overview", ""),
                "units": unit_list,
            }
        )
    return analyses


def _topic_names(rows: list[dict], statuses: set[str]) -> list[str]:
    return [row["topic_name"] for row in rows if (row.get("status") or "pending").lower() in statuses and row.get("topic_name")]


def _top_pending_for_later(rows: list[dict], limit: int = 12) -> list[str]:
    pending = [row for row in rows if (row.get("status") or "pending").lower() == "pending" and row.get("topic_name")]
    pending.sort(key=lambda row: (_difficulty_to_num(row.get("difficulty")), float(row.get("estimated_hours") or 1.0)), reverse=True)
    return [row["topic_name"] for row in pending[:limit]]


def _schedule_day_offsets(schedule: list[dict], start_day: date) -> dict[str, int]:
    offsets: dict[str, int] = {}
    for item in schedule:
        topic = item.get("topic") or ""
        if not topic:
            continue
        try:
            item_day = datetime.fromisoformat(str(item.get("date"))).date()
            offsets[topic] = max(0, (item_day - start_day).days)
        except Exception:
            continue
    return offsets


def _make_plots(metrics: dict, schedule: list[dict], offsets: dict[str, int]) -> None:
    sns.set_theme(style="whitegrid", palette="muted", font_scale=1.05)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    counts = metrics["input_counts"]
    axes[0].bar(counts.keys(), counts.values(), color=["#4f46e5", "#0f766e", "#f59e0b", "#ea580c", "#6b7280"])
    axes[0].set_title("Live Scheduler Input Mix")
    axes[0].set_ylabel("Topics")
    axes[0].tick_params(axis="x", rotation=20)
    for idx, value in enumerate(counts.values()):
        axes[0].text(idx, value + max(1, value * 0.02), str(value), ha="center", va="bottom", fontsize=10)

    scalar_metrics = {
        "coverage": metrics["coverage_ratio"],
        "frontloaded": metrics["frontload_ratio"],
        "llm_used": 1.0 if metrics["planner"]["used_llm"] else 0.0,
        "guidance": metrics["planner"]["topic_guidance_count"],
    }
    axes[1].bar(scalar_metrics.keys(), scalar_metrics.values(), color=["#2563eb", "#16a34a", "#8b5cf6", "#dc2626"])
    axes[1].set_title("Operational Scheduler Signals")
    axes[1].set_ylabel("Score / Count")
    axes[1].tick_params(axis="x", rotation=20)
    for idx, value in enumerate(scalar_metrics.values()):
        label = f"{value:.2f}" if isinstance(value, float) else str(value)
        axes[1].text(idx, value + max(0.02, value * 0.02), label, ha="center", va="bottom", fontsize=10)

    fig.suptitle("LLM Scheduler Evaluation Summary", fontsize=15, fontweight="bold")
    plt.tight_layout()
    fig.savefig(SUMMARY_PLOT, dpi=160, bbox_inches="tight")
    plt.close(fig)

    if schedule:
        df = pd.DataFrame(schedule)
        df["date"] = pd.to_datetime(df["date"])
        day_counts = df.groupby("date").size().reset_index(name="topics")
        day_counts["forced_topics"] = day_counts["date"].map(
            lambda d: sum(1 for topic, offset in offsets.items() if offset == (d.date() - day_counts["date"].min().date()).days)
        )

        fig, ax = plt.subplots(figsize=(15, 6))
        ax.bar(day_counts["date"].dt.strftime("%b %d"), day_counts["topics"], color="#2563eb", label="Scheduled topics")
        if day_counts["forced_topics"].sum() > 0:
            ax.plot(day_counts["date"].dt.strftime("%b %d"), day_counts["forced_topics"], color="#dc2626", marker="o", linewidth=2, label="Forced topics")
        ax.set_title("Schedule Distribution by Day")
        ax.set_ylabel("Topics")
        ax.tick_params(axis="x", rotation=45)
        ax.legend()
        plt.tight_layout()
        fig.savefig(TIMELINE_PLOT, dpi=160, bbox_inches="tight")
        plt.close(fig)


async def _run() -> dict:
    rows = _load_topics()
    if not rows:
        return {"error": "No scheduled_topics rows found"}

    analyses = _build_analyses(rows)
    total_topics = len(rows)
    subject_count = len(analyses)
    completed_topics = _topic_names(rows, {"completed"})
    missed_topics = _topic_names(rows, {"rescheduled"})
    skipped_topics = _topic_names(rows, {"skipped"})
    do_later_topics = _top_pending_for_later(rows, limit=12)

    start_date = date.today() + timedelta(days=1)
    schedule_result = await generate_llm_adaptive_schedule(
        analyses,
        hours_per_day=3.0,
        num_days=21,
        start_date=start_date,
        subject_priorities={analysis["subject_name"]: 3 for analysis in analyses},
        cross_subject_relations=[],
        user_overrides={},
        study_start_hour=9,
        study_end_hour=23,
        stress_level=min(1.0, (len(missed_topics) + len(skipped_topics)) / max(1, total_topics)),
        performance_score=len(completed_topics) / max(1, total_topics),
        completed_topics=completed_topics[:80],
        missed_topics=missed_topics[:80],
        skipped_topics=skipped_topics[:80],
        do_later_topics=do_later_topics,
    )

    schedule = schedule_result.get("schedule", []) or []
    planner = schedule_result.get("planner", {}) or {}
    summary = schedule_result.get("summary", {}) or {}

    offsets = _schedule_day_offsets(schedule, start_date)
    forced_topics = completed_topics[:80] + missed_topics[:80] + skipped_topics[:80] + do_later_topics
    forced_frontloaded = [topic for topic in forced_topics if offsets.get(topic, 999) <= 2]

    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": "rag-llm",
        "source": "scheduled_topics",
        "input_counts": {
            "completed": len(completed_topics),
            "missed": len(missed_topics),
            "skipped": len(skipped_topics),
            "do_later": len(do_later_topics),
            "pending": max(0, total_topics - len(completed_topics) - len(missed_topics) - len(skipped_topics)),
        },
        "planner": {
            "mode": planner.get("mode", "rag-llm"),
            "used_llm": bool(planner.get("used_llm", False)),
            "topic_guidance_count": int(planner.get("topic_guidance_count", 0) or 0),
            "llm_summary": schedule_result.get("llm_summary", {}),
        },
        "subject_count": subject_count,
        "evaluated_topics": sum(len(unit.get("topics", [])) for analysis in analyses for unit in analysis.get("units", [])),
        "total_topics_available": total_topics,
        "scheduled_topics": len(schedule),
        "schedule_days": len({item.get("date") for item in schedule}),
        "coverage_ratio": round(len(schedule) / max(1, total_topics), 4),
        "frontload_ratio": round(len(forced_frontloaded) / max(1, len(forced_topics)), 4),
        "average_difficulty": summary.get("averageDifficulty"),
        "cross_subject_relations": summary.get("crossSubjectRelations", 0),
        "forced_topic_offset_mean": round(
            sum(offsets.get(topic, 0) for topic in forced_topics) / max(1, len(forced_topics)), 4
        ),
        "first_three_days_topics": sum(1 for item in schedule if offsets.get(item.get("topic", ""), 999) <= 2),
        "start_date": schedule_result.get("summary", {}).get("startDate", start_date.isoformat()),
        "end_date": schedule_result.get("summary", {}).get("endDate", ""),
    }

    _ensure_out_dir()
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    _make_plots(metrics, schedule, offsets)
    return metrics


def main() -> None:
    metrics = asyncio.run(_run())
    if metrics.get("error"):
        raise SystemExit(metrics["error"])

    print("\nLLM scheduler metrics")
    print(json.dumps(metrics, indent=2))
    print(f"\nSaved metrics → {METRICS_PATH}")
    print(f"Saved summary plot → {SUMMARY_PLOT}")
    print(f"Saved timeline plot → {TIMELINE_PLOT}")


if __name__ == "__main__":
    main()