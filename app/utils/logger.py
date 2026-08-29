import logging
import sys
import structlog


def setup_logging():
    """
    Configure structlog for application-wide structured logging.
    Fits both standard logging and structlog cleanly without attribute errors.
    """
    # Standard library logging configuration
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    # Structlog processors configuration
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


setup_logging()
logger = structlog.get_logger("shahdol_mvp")

# Compatibility helpers for existing imports
configure_logging = setup_logging

# Helper function to maintain compatibility with `from app.utils.logger import get_logger`
def get_logger(name: str = "shahdol_mvp"):
    return structlog.get_logger(name)
