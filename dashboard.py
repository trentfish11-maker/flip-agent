import argparse
import csv
from collections import defaultdict
from pathlib import Path
from datetime import datetime

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def generate_text_dashboard(results):
    """Generate a text-based dashboard for terminal viewing."""
    print("\n" + "=" * 120)
    print("FLIP AGENT DASHBOARD — TRENDING OPPORTUNITIES")
    print("=" * 120 + "\n")

    # Group by query
    by_query = defaultdict(list)
    for row in results:
        by_query[row.get("query", "")].append(row)

    review_items = [r for r in results if r.get("status") == "REVIEW"]

    if not review_items:
        print("No items ready for review yet. Add sold comparables to sold_comps.csv and try again.\n")
        return

    # Summary stats
    total_potential = sum(parse_float(r.get("estimated_profit", 0)) for r in review_items)
    avg_margin = sum(parse_float(r.get("estimated_margin_pct", 0)) for r in review_items) / len(review_items) if review_items else 0

    print(f"SUMMARY")
    print(f"  Items to review: {len(review_items)}")
    print(f"  Total potential profit: ${total_potential:.2f}")
    print(f"  Average margin: {avg_margin:.1f}%\n")

    # Sort by profit descending
    review_items.sort(key=lambda x: parse_float(x.get("estimated_profit", 0)), reverse=True)

    # Table header
    print(f"{'RANK':<6} {'MARKETPLACE':<15} {'QUERY / TITLE':<30} {'BUY':<10} {'RESALE':<10} {'PROFIT':<10} {'MARGIN':<8} {'COMPS':<6}")
    print("-" * 120)

    for idx, row in enumerate(review_items[:20], 1):  # Top 20
        marketplace = row.get("marketplace", "?")[:12]
        query = row.get("query", "")[:28]
        buy_price = parse_float(row.get("price", 0)) + parse_float(row.get("buy_shipping") or 0)
        resale = parse_float(row.get("estimated_resale", 0))
        profit = parse_float(row.get("estimated_profit", 0))
        margin = parse_float(row.get("estimated_margin_pct", 0))
        comps = row.get("sold_comps", 0)

        print(
            f"{idx:<6} {marketplace:<15} {query:<30} "
            f"${buy_price:<9.2f} ${resale:<9.2f} ${profit:<9.2f} {margin:<7.1f}% {comps:<6}"
        )

    print("\n" + "=" * 120)
    print("DETAILS (Top 5 by profit)")
    print("=" * 120 + "\n")

    for idx, row in enumerate(review_items[:5], 1):
        print(f"{idx}. {row.get('title', 'N/A')}")
        print(f"   URL: {row.get('url', 'N/A')}")
        print(f"   Marketplace: {row.get('marketplace', 'N/A')} | Condition: {row.get('condition', 'N/A').upper()}")
        print(f"   Ask price: ${parse_float(row.get('price', 0)):.2f} + ${parse_float(row.get('buy_shipping') or 0):.2f} shipping = ${parse_float(row.get('price', 0)) + parse_float(row.get('buy_shipping') or 0):.2f} total acquisition")
        print(f"   Median sold price ({row.get('sold_comps')} comps): ${parse_float(row.get('estimated_resale', 0)):.2f}")
        print(f"   Expected profit: ${parse_float(row.get('estimated_profit', 0)):.2f} ({parse_float(row.get('estimated_margin_pct', 0)):.1f}%)")
        print(f"   ⚠️  {row.get('reason', 'N/A')}")
        print()


def generate_chart(results, output_path="flip_dashboard.png"):
    """Generate a visual chart of top opportunities."""
    if not MATPLOTLIB_AVAILABLE:
        print("matplotlib not installed. Run: pip install matplotlib")
        return

    review_items = [r for r in results if r.get("status") == "REVIEW"]
    if not review_items:
        print("No items to chart.")
        return

    review_items.sort(key=lambda x: parse_float(x.get("estimated_profit", 0)), reverse=True)
    top_items = review_items[:12]

    titles = [r.get("title", "")[:25] for r in top_items]
    profits = [parse_float(r.get("estimated_profit", 0)) for r in top_items]
    margins = [parse_float(r.get("estimated_margin_pct", 0)) for r in top_items]
    buy_costs = [parse_float(r.get("price", 0)) + parse_float(r.get("buy_shipping") or 0) for r in top_items]
    resales = [parse_float(r.get("estimated_resale", 0)) for r in top_items]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Flip Agent: Top Trending Opportunities", fontsize=16, fontweight="bold")

    # Chart 1: Profit by item
    ax = axes[0, 0]
    colors = ["#2ecc71" if p > 0 else "#e74c3c" for p in profits]
    ax.barh(titles, profits, color=colors)
    ax.set_xlabel("Expected Profit ($)")
    ax.set_title("Profit Potential (Top 12)")
    ax.grid(axis="x", alpha=0.3)

    # Chart 2: Margin %
    ax = axes[0, 1]
    ax.barh(titles, margins, color="#3498db")
    ax.set_xlabel("Margin (%)")
    ax.set_title("Profit Margin (Top 12)")
    ax.axvline(x=20, color="red", linestyle="--", label="20% Target")
    ax.legend()
    ax.grid(axis="x", alpha=0.3)

    # Chart 3: Buy vs Resale (waterfall-style)
    ax = axes[1, 0]
    x = range(len(titles))
    width = 0.35
    ax.bar([i - width/2 for i in x], buy_costs, width, label="Buy Cost", color="#e74c3c")
    ax.bar([i + width/2 for i in x], resales, width, label="Resale Est.", color="#2ecc71")
    ax.set_ylabel("Price ($)")
    ax.set_title("Buy Price vs. Estimated Resale")
    ax.set_xticks(x)
    ax.set_xticklabels(titles, rotation=45, ha="right", fontsize=8)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Chart 4: Summary stats
    ax = axes[1, 1]
    ax.axis("off")
    total_profit = sum(profits)
    avg_margin = sum(margins) / len(margins) if margins else 0
    total_investment = sum(buy_costs)

    stats_text = f"""
DASHBOARD SUMMARY

Items Reviewed: {len(review_items)}
Top Opportunities: {len(top_items)}

Total Buy Cost (Top 12): ${total_investment:.2f}
Total Profit Potential (Top 12): ${total_profit:.2f}
Average Margin: {avg_margin:.1f}%

Recommendation:
Review the top 3–5 items in detail.
Verify condition, model, authenticity,
and recent sell-through before purchase.

⚠️ This is a research tool, not financial advice.
Always validate sold comparables manually.
    """
    ax.text(0.1, 0.5, stats_text, fontsize=10, verticalalignment="center",
            fontfamily="monospace", bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Chart saved to {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="View flip agent results as chart or dashboard.")
    parser.add_argument("--report", default="report.csv", help="Path to report.csv from flip_agent.py")
    parser.add_argument("--chart", action="store_true", help="Generate PNG chart (requires matplotlib)")
    parser.add_argument("--output", default="flip_dashboard.png", help="Output PNG path")
    args = parser.parse_args()

    results = read_csv(args.report)
    if not results:
        print(f"No results in {args.report}. Run flip_agent.py first.")
        return

    # Always show text dashboard
    generate_text_dashboard(results)

    # Optionally generate chart
    if args.chart:
        generate_chart(results, args.output)


if __name__ == "__main__":
    main()
