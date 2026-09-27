"""One-time Stripe bootstrap: creates the product and the two prices.

Usage:
  STRIPE_SECRET_KEY=sk_test_... python3 scripts/stripe_setup.py

Prints the price IDs to put in .env as STRIPE_PRICE_MONTHLY and
STRIPE_PRICE_QUARTERLY. Run once against test keys, then once against live.
"""

import os
import sys

import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
if not stripe.api_key:
    sys.exit("Set STRIPE_SECRET_KEY first.")

product = stripe.Product.create(
    name="Sunday Strength weekly plan",
    description="Personalised weekly gym plan by email, every Sunday.")

monthly = stripe.Price.create(
    product=product.id, currency="gbp", unit_amount=500,
    recurring={"interval": "month"}, nickname="Monthly £5")

quarterly = stripe.Price.create(
    product=product.id, currency="gbp", unit_amount=1200,
    recurring={"interval": "month", "interval_count": 3},
    nickname="Quarterly £12")

print(f"STRIPE_PRICE_MONTHLY={monthly.id}")
print(f"STRIPE_PRICE_QUARTERLY={quarterly.id}")
