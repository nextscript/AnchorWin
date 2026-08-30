"""Logging setup for AnchorWin (spec §24: 5 MB rotation, max 3 files)."""
import logging
import logging.handlers
from pathlib import Path

LOG_FORMAT = "[%(levelname)s] %(message)s"


def setup_logging(log_dir: Path, console: bool = False) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("anchorwin")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(stream)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("anchorwin")
