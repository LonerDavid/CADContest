"""
Step 4: Strict output formatting — #RESPONSE <id> … #END <id>

Logs are written under output/<case_name>/<case_name>.log (see output_paths.py).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .output_paths import log_path


class ResponseWriter:
    def __init__(self) -> None:
        self.response_id = 0
        self.log_path: Optional[Path] = None
        self.case_name: Optional[str] = None

    def begin_testcase(self, case_name: str) -> None:
        """Reset response counter and open log for a new testcase."""
        self.case_name = case_name
        self.response_id = 0
        self.log_path = log_path(case_name)
        self.log_path.write_text("", encoding="utf-8")

    def emit(self, text: str) -> None:
        self.response_id += 1
        rid = self.response_id
        block = f"#RESPONSE {rid}\n{text}\n#END {rid}\n"
        sys.stdout.write(block)
        sys.stdout.flush()
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(block)
