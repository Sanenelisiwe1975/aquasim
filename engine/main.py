"""AquaSim engine entry point."""
import asyncio
import logging
import signal

import structlog
import uvloop

from engine.core.config import settings
from engine.core.engine import AquaSimEngine


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.log_level == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


async def main() -> None:
    configure_logging()
    log = structlog.get_logger("main")
    log.info("aquasim_starting", mode=settings.mode)

    engine = AquaSimEngine()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(engine._shutdown()))

    await engine.start()


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
