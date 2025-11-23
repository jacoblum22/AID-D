"""
Shared cache statistics logging utility.

Tracks cache hits across all LLM calls for performance analysis.
"""

import json
import os
import sys
from datetime import datetime

# Platform-specific imports for file locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

CACHE_STATS_FILE = "cache_statistics.json"
CACHE_LOCK_FILE = "cache_statistics.lock"


def log_cache_stats(source: str, cached_tokens: int, total_tokens: int, model: str):
    """
    Log cache statistics to a JSON file for analysis with file locking to prevent race conditions.

    Args:
        source: Which component made the call (e.g., "DM_Narrator", "Roll_Analyzer")
        cached_tokens: Number of tokens that were cached
        total_tokens: Total input tokens
        model: Model name (e.g., "gpt-5.1", "gpt-5-nano")
    """
    lock_path = CACHE_LOCK_FILE

    try:
        # Create/open lock file
        lock_file = open(lock_path, "w")

        # Acquire exclusive lock (platform-specific)
        if sys.platform == "win32":
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        # Now safely read, modify, and write
        if os.path.exists(CACHE_STATS_FILE):
            with open(CACHE_STATS_FILE, "r") as f:
                stats = json.load(f)
        else:
            stats = []

        # Add new entry
        stats.append(
            {
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "model": model,
                "cached_tokens": cached_tokens,
                "total_tokens": total_tokens,
                "cache_percentage": (
                    (cached_tokens / total_tokens * 100) if total_tokens > 0 else 0
                ),
            }
        )

        # Save stats atomically
        temp_file = CACHE_STATS_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(stats, f, indent=2)
        os.replace(temp_file, CACHE_STATS_FILE)

    except Exception as e:
        print(f"Warning: Failed to log cache stats: {e}")
    finally:
        # Release lock and close file
        try:
            if sys.platform == "win32":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
        except:
            pass  # Best effort cleanup


def get_cache_summary():
    """
    Get summary statistics of cache performance.

    Returns:
        dict with summary stats (total_calls, total_cached, avg_cache_pct, etc.)
    """
    if not os.path.exists(CACHE_STATS_FILE):
        return {"error": "No cache statistics file found"}

    try:
        with open(CACHE_STATS_FILE, "r") as f:
            stats = json.load(f)

        if not stats:
            return {"error": "No cache statistics recorded"}

        total_calls = len(stats)
        total_cached = sum(s["cached_tokens"] for s in stats)
        total_tokens = sum(s["total_tokens"] for s in stats)
        avg_cache_pct = (total_cached / total_tokens * 100) if total_tokens > 0 else 0

        # Breakdown by source
        by_source = {}
        for stat in stats:
            source = stat["source"]
            if source not in by_source:
                by_source[source] = {"calls": 0, "cached": 0, "total": 0}
            by_source[source]["calls"] += 1
            by_source[source]["cached"] += stat["cached_tokens"]
            by_source[source]["total"] += stat["total_tokens"]

        # Calculate percentages
        for source in by_source:
            by_source[source]["cache_pct"] = (
                by_source[source]["cached"] / by_source[source]["total"] * 100
                if by_source[source]["total"] > 0
                else 0
            )

        return {
            "total_calls": total_calls,
            "total_cached_tokens": total_cached,
            "total_tokens": total_tokens,
            "average_cache_percentage": avg_cache_pct,
            "by_source": by_source,
        }
    except Exception as e:
        return {"error": f"Failed to read cache stats: {e}"}
