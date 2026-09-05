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


def setup_logger():
    logger.remove()

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
