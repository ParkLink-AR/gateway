import logging
import re
import sys

from loguru import logger

from app.config import settings

# Patterns for sensitive data masking in logs
SENSITIVE_PATTERNS = [
    (re.compile(r'(password["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(authorization["\']?\s*[:=]\s*["\']Bearer\s+)([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(secret["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(api_key["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(cardNumber["\']?\s*[:=]\s*["\']?\d{6})(\d{6,10})(\d{4}["\']?)', re.IGNORECASE), r'\1******\3'),
]


def mask_sensitive_data(record):
    msg = record["message"]
    for pattern, replacement in SENSITIVE_PATTERNS:
        msg = pattern.sub(replacement, msg)
    record["message"] = msg
    return True


# The app's live-notifications WebSocket carries the access token in its query string
# (browsers and React Native can't set headers on one), and uvicorn logs every WebSocket's
# full path when it opens.
_QUERY_TOKEN = re.compile(r"(token=)[^&\s\"']+", re.IGNORECASE)


class RedactQueryTokenFilter(logging.Filter):
    """Masks `token=...` in uvicorn's own (stdlib) log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _QUERY_TOKEN.sub(r"\1***REDACTED***", record.msg)
        if record.args:
            args = record.args if isinstance(record.args, tuple) else (record.args,)
            record.args = tuple(
                _QUERY_TOKEN.sub(r"\1***REDACTED***", arg) if isinstance(arg, str) else arg for arg in args
            )
        return True


def setup_logger():
    logger.remove()
    for name in ("uvicorn.error", "uvicorn.access"):
        stdlib_logger = logging.getLogger(name)
        if not any(isinstance(f, RedactQueryTokenFilter) for f in stdlib_logger.filters):
            stdlib_logger.addFilter(RedactQueryTokenFilter())

    if settings.ENVIRONMENT == "development":
        logger.add(
            sys.stdout,
            level="DEBUG",
            filter=mask_sensitive_data,
            format="<green>{time}</green> | <level>{level}</level> | {message}",
        )
    else:
        logger.add(
            sys.stdout,
            level="INFO",
            filter=mask_sensitive_data,
            format="{time} | {level} | {message}",
        )

    return logger
