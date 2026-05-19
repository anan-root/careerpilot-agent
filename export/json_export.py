"""JSON export for job data."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime


def export_json(
    jobs: list[dict],
    output_path: str | Path | None = None,
) -> Path:
    """Export jobs to formatted JSON file."""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = Path(f"data/outputs/jobs_{ts}.json")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    export_data = {
        "generated_at": datetime.now().isoformat(),
        "total_jobs": len(jobs),
        "jobs": jobs,
    }

    output_path.write_text(
        json.dumps(export_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path
