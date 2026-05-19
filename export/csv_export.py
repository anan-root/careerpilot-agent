"""CSV export for job data."""

from __future__ import annotations

import csv
from pathlib import Path
from datetime import datetime

from export.excel import COLUMN_MAP, CORE_COLUMNS


def export_csv(
    jobs: list[dict],
    output_path: str | Path | None = None,
    *,
    include_all_columns: bool = False,
) -> Path:
    """Export jobs to CSV file."""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_path = Path(f"data/outputs/jobs_{ts}.csv")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = list(COLUMN_MAP.keys()) if include_all_columns else CORE_COLUMNS
    header = [COLUMN_MAP.get(c, c) for c in columns]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for job in jobs:
            row = [str(job.get(col, "")) for col in columns]
            writer.writerow(row)

    return output_path
