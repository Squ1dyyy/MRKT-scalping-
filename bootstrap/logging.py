import json
import logging
import logging.handlers
from pathlib import Path
from typing import Optional


class _JsonFormatter(logging.Formatter):
    _EXTRA_FIELDS = ("account", "endpoint", "status", "collection", "price")

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in self._EXTRA_FIELDS:
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


_CONSOLE_FMT = "%(asctime)s.%(msecs)03d  %(levelname)-8s  %(name)-35s  %(message)s"
_CONSOLE_DATE = "%H:%M:%S"


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    root = logging.getLogger("mrkt")
    root.setLevel(level)
    root.propagate = False

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt=_CONSOLE_DATE))
    root.addHandler(console)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        fh.setFormatter(_JsonFormatter())
        root.addHandler(fh)

    # Silence noisy third-party loggers
    for noisy in ("curl_cffi", "tenacity"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
