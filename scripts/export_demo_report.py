"""Export the fixed synthetic report used as a sanitized judge-package sample."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("AETERNUS_DISABLE_BACKGROUND_TASKS", "1")
os.environ.setdefault("AETERNUS_FRONTEND", str(ROOT / "frontend"))
os.environ.setdefault("AETERNUS_DATA", str(ROOT / "data"))

from app import app  # noqa: E402


def main() -> int:
    with app.test_client() as client:
        response = client.post(
            "/api/research/run",
            json={
                "symbol": "AET-DEMO",
                "market": "demo",
                "period": "1y",
                "question": (
                    "Assess whether the synthetic company's improving momentum is "
                    "supported by risk and SMA crossover backtest evidence."
                ),
                "demo_mode": True,
                "prefer_gpt": False,
            },
        )
    if response.status_code != 200:
        raise RuntimeError(f"Fixed Demo export failed with HTTP {response.status_code}.")
    report = response.get_json()
    if (
        report.get("gpt_used") is not False
        or report.get("data_mode") != "synthetic_demo"
    ):
        raise RuntimeError("The exported report is not the labeled deterministic fallback.")
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if re.search(r"\bsk-[A-Za-z0-9_-]{12,}\b|authorization\s*:\s*bearer", serialized, re.I):
        raise RuntimeError("Credential-like content was detected in the sample report.")
    output = ROOT / "docs" / "SAMPLE_RESEARCH_REPORT.json"
    output.write_text(serialized + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "pass": True,
                "file": "docs/SAMPLE_RESEARCH_REPORT.json",
                "tools": len(report.get("tool_timeline") or []),
                "evidence": len(report.get("evidence_catalog") or []),
                "data_as_of": report.get("data_as_of"),
                "gpt_used": report.get("gpt_used"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
