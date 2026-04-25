"""Single place to configure root logging.

Call `configure_logging()` once at process start (the CLI does this in
`cli.main()`). Library modules should only do `logging.getLogger(__name__)`.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_configured = False


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(_FORMAT)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _configured = True
