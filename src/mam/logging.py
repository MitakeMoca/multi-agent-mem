"""Lightweight logging utilities using only the standard library."""

from __future__ import annotations

import sys
import time

__all__ = ["log", "TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "LogLevel", "set_level"]

TRACE = 5
DEBUG = 10
INFO = 20
WARNING = 30
ERROR = 40
CRITICAL = 50

_current_level = INFO

def set_level(level: int) -> None:
    global _current_level
    _current_level = level

def log(message: str, level: int = INFO, *, name: str | None = None, file: object = sys.stderr) -> None:
    if level < _current_level:
        return
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    prefix = f"[{timestamp}] {name or 'mam'}"
    if level >= ERROR:
        prefix += " ERROR"
    elif level >= WARNING:
        prefix += " WARN"
    elif level >= DEBUG:
        prefix += " DEBUG"
    print(f"{prefix} {message}", file=file)
