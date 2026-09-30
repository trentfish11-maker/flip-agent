import argparse
import base64
import csv
import os
import statistics
from collections import defaultdict
from pathlib import Path

import requests

EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


def number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value):
    """Handle eBay money objects or plain CSV numbers."""
    if isinstance(value, dict):
        return number(value.get("value"))
    return number(value)


def ebay_token():
    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET to search eBay."
        )

    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()

    response = requests.post(
        EBAY_TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def search_ebay(query, token, limit):
    response = requests.get(
        EBAY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        },
        params={"q": query, "limit": limit},
        timeout=20,
    )
    response.raise_for_status()

    for item in response.json().get("itemSummaries", []):
        shipping_options = item.get("shippingOptions") or []
        shipping_cost = None

        if shipping_options:
            cost = shipping_options[0].get("shippingCost")
            if cost is not None:
                shipping_cost = money(cost)

        yield {
            "marketplace": "eBay",
            "query": query,
            "title": item.get("title", ""),
            "condition": item.get("condition", "").strip().lower(),
            "price": money(item.get("price")),
            "buy_shipping": shipping_cost,
            "url": item.get("itemWebUrl", ""),
        }


def read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def sold_comparables(path):
    groups = defaultdict(list)

    for row in read_csv(path):
        query = row.get("query", "").strip().lower()
        condition = row.get("condition", "").strip().lower()
        sold_price = number(row.get("sold_price"))
        if query and condition and sold_price > 0:
            groups[(query, condition)].append(sold_price)

    return groups


def manual_listings(path):
    for row in read_csv(path):
        yield {
            "marketplace": row.get("marketplace", "Manual").strip(),
            "query": row.get("query", "").strip(),
            "title": row.get("title", "").strip(),
            "condition": row.get("condition", "").strip().lower(),
            "price": number(row.get("price")),
            "buy_shipping": number(row.get("buy_shipping")),
            "url": row.get("url", "").strip(),
        }


def evaluate(item, comparables, args):
    key = (item["query"].lower(), item["condition"])
    prices = comparables.get(key, [])
    reasons = []

    if len(prices) < 3:
        reasons.append("Fewer than 3 matching sold comparables")
    if not item["condition"]:
        reasons.append("Condition missing")
    if item["price"] <= 0:
        reasons.append("Listing price missing")
    if item["buy_shipping"] is None:
        reasons.append("Purchase shipping unknown")
    if not item["url"]:
        reasons.append("Source URL missing")

    # An exact search term and condition are minimum checks, not proof
    # that the sold items have the same model, size, or authenticity.
    resale = statistics.median(prices) if prices else 0.0
    acquisition = item["price"] + (item["buy_shipping"] or 0)
    fee = resale * args.fee_rate + args.fixed_fee
    profit = (
        resale
        - acquisition
        - fee
        - args.outbound_shipping
        - args.supplies
        - args.risk_allowance
    )
    margin = profit / resale if resale > 0 else 0.0

    if len(prices) >= 3 and profit < args.min_profit:
        reasons.append("Estimated profit below target")
    if len(prices) >= 3 and margin < args.min_margin:
        reasons.append("Estimated margin below target")

    status = "REVIEW" if not reasons else "PASS"
    explanation = (
        f"Median of {len(prices)} sold comps: ${resale:.2f}; "
        f"buy cost: ${acquisition:.2f}; estimated fees: ${fee:.2f}; "
        f"outbound shipping: ${args.outbound_shipping:.2f}; "
        f"supplies: ${args.supplies:.2f}; "
        f"risk allowance: ${args.risk_allowance:.2f}. "
        + ("Check exact model, condition, authenticity, and sell-through."
           if status == "REVIEW" else "; ".join(reasons) + ".")
    )

    return {
        **item,
        "sold_comps": len(prices),
        "estimated_resale": round(resale, 2),
        "estimated_profit": round(profit, 2),
        "estimated_margin_pct": round(margin * 100, 1),
        "status": status,
        "reason": explanation,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Research potential resale flips; never purchases items."
    )
    parser.add_argument("--queries", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--sold", default="sold_comps.csv")
    parser.add_argument("--manual", default="manual_listings.csv")
    parser.add_argument("--output", default="report.csv")
    parser.add_argument("--fee-rate", type=float, default=0.15)
    parser.add_argument("--fixed-fee", type=float, default=0.40)
    parser.add_argument("--outbound-shipping", type=float, default=8.00)
    parser.add_argument("--supplies", type=float, default=2.00)
    parser.add_argument("--risk-allowance", type=float, default=5.00)
    parser.add_argument("--min-profit", type=float, default=20.00)
    parser.add_argument("--min-margin", type=float, default=0.20)
    args = parser.parse_args()

    if not 1 <= args.limit <= 200:
        parser.error("--limit must be between 1 and 200")

    items = list(manual_listings(args.manual))
    if args.queries:
        token = ebay_token()
        for query in args.queries:
            items.extend(search_ebay(query, token, args.limit))

    if not items:
        parser.error("Supply --queries or add rows to manual_listings.csv")

    comps = sold_comparables(args.sold)
    results = [evaluate(item, comps, args) for item in items]
    results.sort(
        key=lambda row: (
            row["status"] != "REVIEW",
            -row["estimated_profit"],
        )
    )

    with open(args.output, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    review_count = sum(row["status"] == "REVIEW" for row in results)
    print(f"Checked {len(results)} listings; {review_count} to review.")
    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
