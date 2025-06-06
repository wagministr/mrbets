#!/usr/bin/env python
"""
Continuous Fetchers Daemon

This daemon continuously runs all fetcher modules in coordinated intervals to collect data
from various sources (Twitter, news sites, odds APIs) and populate the Redis stream.

Usage:
    python -m schedulers.continuous_fetchers

Features:
- Smart intervals based on source priority
- Coordination to avoid conflicts
- Error handling and recovery
- Monitoring and health checks
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

# Import fetchers
from fetchers.twitter_fetcher import main_twitter_task as twitter_main_task
from fetchers.scraper_fetcher import main_scraper_task as scraper_main_task  
from fetchers.odds_fetcher import main as odds_main_task
from fetchers.rest_fetcher import fetch as rest_fetch_function

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("continuous_fetchers")

# Load environment variables
load_dotenv()

# Configuration
FETCHER_INTERVALS = {
    "twitter": {
        "high_priority_accounts": ["FabrizioRomano", "OptaJoe", "SkySports"],
        "interval_seconds": 120,  # 2 minutes for high priority
        "fallback_interval": 300  # 5 minutes for general
    },
    "scraper": {
        "interval_seconds": 600,  # 10 minutes for news scraping
        "max_pages_per_run": 3
    },
    "odds": {
        "interval_seconds": 900,  # 15 minutes for odds
        "sports": ["football"]
    },
    "rest": {
        "interval_seconds": 1800,  # 30 minutes for detailed match data
        "max_fixtures_per_run": 20
    }
}

# Global scheduler and running flag
scheduler: Optional[AsyncIOScheduler] = None
running = True
fetcher_stats = {
    "twitter": {"last_run": None, "success_count": 0, "error_count": 0},
    "scraper": {"last_run": None, "success_count": 0, "error_count": 0},
    "odds": {"last_run": None, "success_count": 0, "error_count": 0},
    "rest": {"last_run": None, "success_count": 0, "error_count": 0}
}


def signal_handler(sig, frame):
    """Handle signals to gracefully shut down the daemon"""
    global running, scheduler
    logger.info("Shutdown signal received, stopping all fetchers...")
    running = False
    if scheduler:
        scheduler.shutdown()


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


async def run_twitter_fetcher():
    """Run Twitter fetcher with error handling"""
    fetcher_name = "twitter"
    try:
        logger.info("Starting Twitter fetcher...")
        fetcher_stats[fetcher_name]["last_run"] = datetime.utcnow()
        
        # Run twitter fetcher with both expert monitoring and keyword search
        await twitter_main_task(mode="both", hours_back=2)
        
        fetcher_stats[fetcher_name]["success_count"] += 1
        logger.info("Twitter fetcher completed successfully")
        
    except Exception as e:
        fetcher_stats[fetcher_name]["error_count"] += 1
        logger.error(f"Error in Twitter fetcher: {e}", exc_info=True)


async def run_scraper_fetcher():
    """Run news scraper fetcher with error handling"""
    fetcher_name = "scraper"
    try:
        logger.info("Starting scraper fetcher...")
        fetcher_stats[fetcher_name]["last_run"] = datetime.utcnow()
        
        # Run scraper with no specific fixture_id (general scan)
        await scraper_main_task()
        
        fetcher_stats[fetcher_name]["success_count"] += 1
        logger.info("Scraper fetcher completed successfully")
        
    except Exception as e:
        fetcher_stats[fetcher_name]["error_count"] += 1
        logger.error(f"Error in scraper fetcher: {e}", exc_info=True)


async def run_odds_fetcher():
    """Run odds fetcher with error handling"""
    fetcher_name = "odds"
    try:
        logger.info("Starting odds fetcher...")
        fetcher_stats[fetcher_name]["last_run"] = datetime.utcnow()
        
        # Run odds fetcher
        await odds_main_task()
        
        fetcher_stats[fetcher_name]["success_count"] += 1
        logger.info("Odds fetcher completed successfully")
        
    except Exception as e:
        fetcher_stats[fetcher_name]["error_count"] += 1
        logger.error(f"Error in odds fetcher: {e}", exc_info=True)


async def run_rest_fetcher():
    """Run REST API fetcher with error handling"""
    fetcher_name = "rest"
    try:
        logger.info("Starting REST fetcher...")
        fetcher_stats[fetcher_name]["last_run"] = datetime.utcnow()
        
        # REST fetcher needs specific fixture IDs, so we'll skip it for now
        # TODO: Get recent fixture IDs from database and process them
        # For now, we'll just log that it would run
        logger.info("REST fetcher skipped - requires specific fixture IDs")
        
        fetcher_stats[fetcher_name]["success_count"] += 1
        logger.info("REST fetcher completed (skipped - no general scan available)")
        
    except Exception as e:
        fetcher_stats[fetcher_name]["error_count"] += 1
        logger.error(f"Error in REST fetcher: {e}", exc_info=True)


async def health_check():
    """Perform health check and log statistics"""
    try:
        logger.info("=== Fetcher Health Check ===")
        for fetcher_name, stats in fetcher_stats.items():
            last_run = stats["last_run"]
            if last_run:
                time_since_last = datetime.utcnow() - last_run
                logger.info(f"{fetcher_name}: last_run={time_since_last.total_seconds():.0f}s ago, "
                          f"success={stats['success_count']}, errors={stats['error_count']}")
            else:
                logger.info(f"{fetcher_name}: never run")
        
        # Check for stale fetchers (haven't run in expected interval * 2)
        stale_fetchers = []
        for fetcher_name, config in FETCHER_INTERVALS.items():
            stats = fetcher_stats[fetcher_name]
            if stats["last_run"]:
                expected_interval = config["interval_seconds"]
                time_since_last = datetime.utcnow() - stats["last_run"]
                if time_since_last.total_seconds() > expected_interval * 2:
                    stale_fetchers.append(fetcher_name)
        
        if stale_fetchers:
            logger.warning(f"Stale fetchers detected: {stale_fetchers}")
        
        logger.info("=== Health Check Complete ===")
        
    except Exception as e:
        logger.error(f"Error in health check: {e}", exc_info=True)


def setup_scheduler():
    """Setup the APScheduler with all fetcher jobs"""
    global scheduler
    
    scheduler = AsyncIOScheduler()
    
    # Add Twitter fetcher (high frequency)
    scheduler.add_job(
        run_twitter_fetcher,
        trigger=IntervalTrigger(seconds=FETCHER_INTERVALS["twitter"]["interval_seconds"]),
        id="twitter_fetcher",
        name="Twitter Fetcher",
        max_instances=1,
        coalesce=True
    )
    
    # Add Scraper fetcher (medium frequency)
    scheduler.add_job(
        run_scraper_fetcher,
        trigger=IntervalTrigger(seconds=FETCHER_INTERVALS["scraper"]["interval_seconds"]),
        id="scraper_fetcher", 
        name="Scraper Fetcher",
        max_instances=1,
        coalesce=True
    )
    
    # Add Odds fetcher (medium frequency)
    scheduler.add_job(
        run_odds_fetcher,
        trigger=IntervalTrigger(seconds=FETCHER_INTERVALS["odds"]["interval_seconds"]),
        id="odds_fetcher",
        name="Odds Fetcher", 
        max_instances=1,
        coalesce=True
    )
    
    # Add REST fetcher (low frequency)
    scheduler.add_job(
        run_rest_fetcher,
        trigger=IntervalTrigger(seconds=FETCHER_INTERVALS["rest"]["interval_seconds"]),
        id="rest_fetcher",
        name="REST Fetcher",
        max_instances=1,
        coalesce=True
    )
    
    # Add health check (every 5 minutes)
    scheduler.add_job(
        health_check,
        trigger=IntervalTrigger(seconds=300),
        id="health_check",
        name="Health Check",
        max_instances=1,
        coalesce=True
    )
    
    logger.info("Scheduler configured with all fetcher jobs")


async def run_initial_fetchers():
    """Run all fetchers once at startup"""
    logger.info("Running initial fetch cycle...")
    
    # Run fetchers in sequence with delays to avoid overwhelming APIs
    await run_scraper_fetcher()
    await asyncio.sleep(10)
    
    await run_odds_fetcher()  
    await asyncio.sleep(10)
    
    await run_rest_fetcher()
    await asyncio.sleep(10)
    
    await run_twitter_fetcher()
    
    logger.info("Initial fetch cycle completed")


async def main():
    """Main daemon function"""
    logger.info("Starting Continuous Fetchers Daemon...")
    
    # Setup the scheduler
    setup_scheduler()
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started")
    
    # Run initial fetchers
    await run_initial_fetchers()
    
    # Keep the daemon running
    try:
        while running:
            await asyncio.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    
    finally:
        logger.info("Shutting down scheduler...")
        if scheduler:
            scheduler.shutdown()
        logger.info("Continuous Fetchers Daemon stopped")


if __name__ == "__main__":
    asyncio.run(main()) 