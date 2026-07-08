#!/usr/bin/env python
"""Entry point for the hourly cron / scheduled task.

    python scripts/run_hourly.py

Schedule examples:
  cron:        0 * * * *  /path/to/venv/bin/python /path/to/scripts/run_hourly.py
  Azure Func:  timer trigger "0 0 * * * *" calling quoteai_mcp.pipeline.run_once
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quoteai_mcp.pipeline import main  # noqa: E402

if __name__ == "__main__":
    main()
