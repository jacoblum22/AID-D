"""
Quick script to check cache statistics.

Run this to see how well caching is performing across all LLM calls.
"""

from cache_logger import get_cache_summary
import sys


def main():
    print("=" * 70)
    print("CACHE STATISTICS SUMMARY")
    print("=" * 70 + "\n")

    try:
        summary = get_cache_summary()
    except Exception as e:
        print(f"❌ Error retrieving cache summary: {e}")
        sys.exit(1)

    if "error" in summary:
        print(f"❌ Error: {summary['error']}")
        sys.exit(1)

    # Overall stats (with validation)
    print(f"📊 OVERALL STATISTICS:")
    print(f"   Total API calls: {summary.get('total_calls', 0)}")
    print(f"   Total tokens processed: {summary.get('total_tokens', 0):,}")
    print(f"   Total tokens cached: {summary.get('total_cached_tokens', 0):,}")
    print(
        f"   Average cache hit rate: {summary.get('average_cache_percentage', 0):.1f}%\n"
    )

    # Breakdown by source (with validation)
    by_source = summary.get("by_source", {})
    if by_source:
        print(f"📋 BREAKDOWN BY SOURCE:")
        print("-" * 70)

        for source in sorted(by_source.keys()):  # type: ignore
            stats = by_source[source]  # type: ignore
            print(f"\n{source}:")
            print(f"   Calls: {stats.get('calls', 0)}")  # type: ignore
            print(f"   Total tokens: {stats.get('total', 0):,}")  # type: ignore
            print(f"   Cached tokens: {stats.get('cached', 0):,}")  # type: ignore
            print(f"   Cache rate: {stats.get('cache_pct', 0):.1f}%")  # type: ignore

    print("\n" + "=" * 70)

    # Calculate cost savings (rough estimate)
    # Cached tokens are typically 50% cheaper
    # Note: gpt-5-nano is a real OpenAI model (released Aug 2025)
    input_cost_per_1k = 0.01  # Rough estimate for gpt-5-nano input tokens
    tokens_saved = summary.get("total_cached_tokens", 0)  # type: ignore
    cost_saved = (tokens_saved / 1000) * (input_cost_per_1k * 0.5)  # type: ignore

    print(f"\n💰 ESTIMATED COST SAVINGS:")
    print(f"   Tokens saved by caching: {tokens_saved:,}")
    print(f"   Approximate cost saved: ${cost_saved:.4f}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
