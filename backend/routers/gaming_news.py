"""
Gaming News Router - RSS Aggregator
Fetches latest gaming headlines from multiple RSS feeds
Optimized for Dewey to reference when users ask about gaming news
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional
import httpx
import feedparser
from datetime import datetime, timedelta
import logging
from email.utils import parsedate_to_datetime

router = APIRouter()
logger = logging.getLogger(__name__)

# Gaming news RSS feeds
RSS_FEEDS = {
    "ign": {
        "url": "https://feeds.ign.com/ign/all",
        "name": "IGN"
    },
    "gamespot": {
        "url": "https://www.gamespot.com/feeds/mashup/",
        "name": "GameSpot"
    },
    "polygon": {
        "url": "https://www.polygon.com/rss/index.xml",
        "name": "Polygon"
    },
    "pcgamer": {
        "url": "https://www.pcgamer.com/rss/",
        "name": "PC Gamer"
    },
    "kotaku": {
        "url": "https://kotaku.com/rss",
        "name": "Kotaku"
    },
    "eurogamer": {
        "url": "https://www.eurogamer.net/?format=rss",
        "name": "Eurogamer"
    },
    "destructoid": {
        "url": "https://www.destructoid.com/feed/",
        "name": "Destructoid"
    }
}

# Cache configuration
CACHE_DURATION_HOURS = 12
_headlines_cache: Optional[List[Dict]] = None
_cache_timestamp: Optional[datetime] = None


def is_cache_valid() -> bool:
    """Check if the cache is still valid."""
    if _headlines_cache is None or _cache_timestamp is None:
        return False

    age = datetime.now() - _cache_timestamp
    return age < timedelta(hours=CACHE_DURATION_HOURS)


def parse_rss_date(date_string: str) -> Optional[datetime]:
    """Parse various RSS date formats to datetime."""
    if not date_string:
        return None

    try:
        # Try RFC 2822 format (most common in RSS)
        return parsedate_to_datetime(date_string)
    except Exception:
        try:
            # Try ISO format
            return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        except Exception:
            return None


async def fetch_feed(source_key: str, feed_info: Dict) -> List[Dict]:
    """Fetch and parse a single RSS feed."""
    headlines = []

    try:
        logger.info(f"[fetch_feed] Fetching {feed_info['name']} from {feed_info['url']}")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(feed_info["url"])
            response.raise_for_status()

            # Parse RSS feed
            feed = feedparser.parse(response.text)

            if not feed.entries:
                logger.warning(f"[fetch_feed] {feed_info['name']} returned no entries")

            for entry in feed.entries:
                # Parse published date
                pub_date = None
                if hasattr(entry, 'published'):
                    pub_date = parse_rss_date(entry.published)
                elif hasattr(entry, 'updated'):
                    pub_date = parse_rss_date(entry.updated)

                # Get description/summary
                description = ""
                if hasattr(entry, 'summary'):
                    description = entry.summary
                elif hasattr(entry, 'description'):
                    description = entry.description

                # Get author
                author = entry.get('author', '') if hasattr(entry, 'author') else ''

                # Get categories/tags
                categories = []
                if hasattr(entry, 'tags'):
                    categories = [tag.get('term', '') for tag in entry.tags]

                headline = {
                    "source": feed_info["name"],
                    "source_key": source_key,
                    "title": entry.title if hasattr(entry, 'title') else '',
                    "url": entry.link if hasattr(entry, 'link') else '',
                    "published": pub_date.isoformat() if pub_date else None,
                    "published_relative": get_relative_time(pub_date) if pub_date else "Unknown",
                    "author": author,
                    "summary": description[:500] if description else "",  # Limit summary length
                    "categories": categories
                }

                headlines.append(headline)

        logger.info(f"Fetched {len(headlines)} headlines from {feed_info['name']}")

    except Exception as e:
        logger.error(f"Failed to fetch {feed_info['name']}: {e}")

    return headlines


def get_relative_time(dt: datetime) -> str:
    """Convert datetime to relative time string (e.g., '2 hours ago')."""
    if not dt:
        return "Unknown"

    # Make datetime timezone-aware if it isn't
    if dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(dt.tzinfo)
    diff = now - dt

    seconds = diff.total_seconds()

    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"


async def fetch_all_headlines() -> List[Dict]:
    """Fetch headlines from all RSS feeds."""
    global _headlines_cache, _cache_timestamp

    # Return cached data if valid
    if is_cache_valid():
        logger.info(f"Returning cached headlines ({len(_headlines_cache)} items)")
        return _headlines_cache

    logger.info("Fetching fresh headlines from all RSS feeds...")

    all_headlines = []

    # Fetch from all feeds
    for source_key, feed_info in RSS_FEEDS.items():
        headlines = await fetch_feed(source_key, feed_info)
        all_headlines.extend(headlines)

    # Sort by published date (newest first)
    all_headlines.sort(
        key=lambda x: x['published'] if x['published'] else '1970-01-01',
        reverse=True
    )

    # Update cache
    _headlines_cache = all_headlines
    _cache_timestamp = datetime.now()

    # Log headlines per source
    from collections import Counter
    source_counts = Counter(h["source_key"] for h in all_headlines)
    logger.info(f"Fetched total of {len(all_headlines)} headlines from {len(RSS_FEEDS)} sources")
    logger.info(f"Headlines per source: {dict(source_counts)}")

    return all_headlines


@router.get("/headlines")
async def get_headlines(
    limit: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None, description="Filter by source (e.g., 'ign', 'gamespot')"),
    search: Optional[str] = Query(None, description="Search in title or summary"),
    hours: Optional[int] = Query(None, description="Only show news from last N hours")
) -> Dict:
    """
    Get latest gaming headlines from multiple RSS feeds.

    Args:
        limit: Maximum number of headlines to return (1-100, default: 20)
        source: Filter by source key (ign, gamespot, polygon, pcgamer, kotaku, eurogamer, destructoid)
        search: Search keyword in title or summary
        hours: Only show news from last N hours

    Returns:
        {
            "headlines": [...],
            "count": 20,
            "sources": ["IGN", "GameSpot", ...],
            "cached": true,
            "cache_age_minutes": 45,
            "total_available": 150
        }
    """
    headlines = await fetch_all_headlines()
    total_available = len(headlines)

    logger.info(f"[get_headlines] Total headlines before filtering: {total_available}")

    # Filter by source
    if source:
        before_count = len(headlines)
        headlines = [h for h in headlines if h["source_key"].lower() == source.lower()]
        logger.info(f"[get_headlines] Source filter '{source}': {before_count} -> {len(headlines)} headlines")

    # Filter by time range
    if hours:
        from datetime import timezone
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        filtered_headlines = []
        for h in headlines:
            if not h["published"]:
                continue
            try:
                pub_dt = datetime.fromisoformat(h["published"])
                # Make timezone-aware if needed
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt > cutoff:
                    filtered_headlines.append(h)
            except Exception as e:
                logger.warning(f"[get_headlines] Failed to parse date: {e}")
                continue
        headlines = filtered_headlines

    # Search in title or summary
    if search:
        search_lower = search.lower()
        headlines = [
            h for h in headlines
            if search_lower in h["title"].lower() or search_lower in h["summary"].lower()
        ]

    # Limit results
    headlines = headlines[:limit]

    # Get unique sources
    sources = list(set(h["source"] for h in headlines))

    # Calculate cache age
    cache_age_minutes = 0
    if _cache_timestamp:
        cache_age_minutes = int((datetime.now() - _cache_timestamp).total_seconds() / 60)

    return {
        "headlines": headlines,
        "count": len(headlines),
        "sources": sorted(sources),
        "cached": is_cache_valid(),
        "cache_age_minutes": cache_age_minutes,
        "total_available": total_available
    }


@router.get("/sources")
async def get_sources() -> Dict:
    """Get list of available RSS news sources."""
    return {
        "sources": [
            {
                "key": key,
                "name": info["name"],
                "url": info["url"]
            }
            for key, info in RSS_FEEDS.items()
        ],
        "count": len(RSS_FEEDS)
    }


@router.get("/trending")
async def get_trending(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(10, ge=1, le=50)
) -> Dict:
    """
    Get trending topics from recent headlines.
    Useful for Dewey to answer "What's trending in gaming?"

    Args:
        hours: Look at news from last N hours (default: 24)
        limit: Number of results (default: 10)
    """
    headlines = await fetch_all_headlines()
    logger.info(f"[get_trending] Total headlines available: {len(headlines)}")

    # Filter to recent news
    from datetime import timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    logger.info(f"[get_trending] Cutoff time: {cutoff} (last {hours} hours)")

    recent = []
    for h in headlines:
        if not h["published"]:
            continue
        try:
            pub_dt = datetime.fromisoformat(h["published"])
            # Make timezone-aware if needed
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if pub_dt > cutoff:
                recent.append(h)
        except Exception as e:
            logger.warning(f"[get_trending] Failed to parse date for headline: {e}")
            continue

    logger.info(f"[get_trending] Recent headlines (last {hours}h): {len(recent)}")

    # Count keyword frequency in titles
    from collections import Counter

    # Extract important words from titles (ignore common words)
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'was', 'be', 'has', 'have', 'had', 'this', 'that', 'from', 'as', 'it', 'its'}

    words = []
    for h in recent:
        title_words = h["title"].lower().split()
        words.extend([w.strip('.,!?;:()[]{}') for w in title_words if len(w) > 3 and w.lower() not in stop_words])

    word_freq = Counter(words)
    trending_words = word_freq.most_common(20)

    return {
        "timeframe_hours": hours,
        "articles_analyzed": len(recent),
        "trending_keywords": [{"word": word, "mentions": count} for word, count in trending_words],
        "top_headlines": recent[:limit]
    }


@router.post("/refresh")
async def refresh_cache() -> Dict:
    """Force refresh the headlines cache."""
    global _headlines_cache, _cache_timestamp

    # Invalidate cache
    _headlines_cache = None
    _cache_timestamp = None

    # Fetch fresh data
    headlines = await fetch_all_headlines()

    return {
        "success": True,
        "headlines_count": len(headlines),
        "sources_count": len(RSS_FEEDS),
        "timestamp": _cache_timestamp.isoformat() if _cache_timestamp else None
    }


@router.get("/stats")
async def get_stats() -> Dict:
    """Get cache and feed statistics."""
    # Get per-source counts
    source_breakdown = {}
    if _headlines_cache:
        from collections import Counter
        source_counts = Counter(h["source_key"] for h in _headlines_cache)
        source_breakdown = {
            key: {
                "name": RSS_FEEDS[key]["name"],
                "count": source_counts.get(key, 0),
                "url": RSS_FEEDS[key]["url"]
            }
            for key in RSS_FEEDS.keys()
        }

    return {
        "cache_valid": is_cache_valid(),
        "cached_count": len(_headlines_cache) if _headlines_cache else 0,
        "cache_timestamp": _cache_timestamp.isoformat() if _cache_timestamp else None,
        "cache_age_minutes": int((datetime.now() - _cache_timestamp).total_seconds() / 60) if _cache_timestamp else None,
        "cache_duration_hours": CACHE_DURATION_HOURS,
        "rss_sources": len(RSS_FEEDS),
        "sources": list(RSS_FEEDS.keys()),
        "source_breakdown": source_breakdown
    }
