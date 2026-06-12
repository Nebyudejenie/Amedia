"""RSS scheduler worker — runs process_all_feeds() on a fixed interval.

Runs as a standalone container (see docker-compose rss-worker service).
Per-feed cadence and exponential backoff live in next_fetch_at, so this
job just sweeps for whatever is due.
"""
import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from clients import PostgreSQLPool
from services.rss_fetcher import FETCH_INTERVAL_MINUTES, process_all_feeds

logger = logging.getLogger(__name__)


async def run_cycle() -> None:
    """One sweep; never raises (a failed cycle must not kill the scheduler)."""
    try:
        result = await process_all_feeds()
        if result["processed"]:
            logger.info(f"RSS sweep: {result}")
    except Exception:
        logger.exception("RSS sweep failed")


async def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info(f"RSS worker starting (interval: {FETCH_INTERVAL_MINUTES}m)")

    await PostgreSQLPool.init()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_cycle,
        IntervalTrigger(minutes=FETCH_INTERVAL_MINUTES),
        id="rss_sweep",
        max_instances=1,       # never overlap sweeps
        coalesce=True,         # collapse missed runs into one
        misfire_grace_time=60,
    )
    scheduler.start()

    # Kick off an immediate first sweep instead of waiting a full interval
    await run_cycle()

    try:
        await asyncio.Event().wait()  # run forever
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("RSS worker stopping")
    finally:
        scheduler.shutdown(wait=False)
        await PostgreSQLPool.close()


if __name__ == "__main__":
    asyncio.run(main())
