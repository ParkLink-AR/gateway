import sys

from loguru import logger

from app.config import settings


def setup_logger():
    logger.remove()

    if settings.ENVIRONMENT == "development":
        logger.add(
            sys.stdout,
            level="DEBUG",
            format="<green>{time}</green> | <level>{level}</level> | {message}",
        )
    else:
        logger.add(
            sys.stdout,
            level="INFO",
            format="{time} | {level} | {message}",
        )

    return logger
