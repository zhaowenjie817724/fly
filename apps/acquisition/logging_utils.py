from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(level: str, log_dir: Path, run_id: str) -> logging.Logger:
    logger = logging.getLogger("acquisition")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_dir.mkdir(parents=True, exist_ok=True)
    file_path = log_dir / f"run_{run_id}.log"
    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
