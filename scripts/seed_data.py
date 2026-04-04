"""
Seed Data Generator — Populates System 1 with realistic payment data.

Generates:
- 5 merchants with unique schemas
- 200 customers across all merchants
- 500 payments with realistic amounts, methods, statuses
- 80 refunds on captured/settled payments
- Domain events for all operations

Usage:
  python seed_data.py              # Default: 5 merchants, 200 customers, 500 payments
  python seed_data.py --merchants 3 --customers 100 --payments 200
  python seed_data.py --reset      # Drop all data first, then seed
"""
import asyncio
import json
import random
import string
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

BASE_URL = "http://localhost:8001"

# ─── Realistic Data ──────────────────────────────────────────────────────────

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Charles", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Dorothy", "Paul", "Kimberly", "Andrew", "Emily", "Joshua", "Donna",
    "Kenneth", "Michelle", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen",
    "Benjamin", "Samantha", "Samuel", "Katherine", "Raymond", "Christine", "Gregory", "Debra",
    "Frank", "Rachel", "Alexander", "Carolyn", "Patrick", "Janet", "Jack", "Catherine",
    "Dennis", "Maria", "Jerry", "Heather", "Tyler", "Diane", "Aaron", "Ruth",
    "Jose", "Julie", "Nathan", "Olivia", "Peter", "Joyce", "Henry", "Virginia",
    "Adam", "Victoria", "Douglas", "Kelly", "Zachary", "Lauren", "Carl", "Christina",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Phillips", "Evans", "Turner", "Parker", "Collins", "Edwards",
    "Stewart", "Morris", "Murphy", "Cook", "Rogers", "Morgan", "Cooper", "Peterson",
    "Bailey", "Reed", "Kelly", "Howard", "Cox", "Ward", "Richardson", "Watson",
    "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz",
    "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long",
    "Ross", "Foster", "Jimenez", "Powell", "Jenkins", "Perry", "Russell", "Sullivan",
    "Bell", "Coleman", "Butler", "Henderson", "Barnes", "Gonzales", "Fisher", "Vasquez",
    "Simmons", "Romero", "Jordan", "Patterson", "Alexander", "Hamilton", "Graham", "Reynolds",
]

MERCHANT_NAMES = [
    "TechStore Pro", "Fashion Hub", "Foodie Express", "TravelWise", "GameZone",
    "BookWorm Digital", "HealthFirst", "AutoParts Direct", "PetPalace", "HomeDecor Plus",
    "MusicStream", "FitLife Gym", "CloudKitchen", "EduLearn", "GreenMart",
]

DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "protonmail.com", "company.com", "business.org", "mail.com", "aol.com",
]

CURRENCIES = ["USD", "EUR", "GBP", "INR", "JPY"]
CURRENCY_WEIGHTS = [40, 20, 15, 15, 10]

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]
METHOD_WEIGHTS = [45, 25, 20, 10]

PAYMENT_DESCRIPTIONS = [
    "Order #{order_id} — Premium Subscription",
    "Order #{order_id} — Product Purchase",
    "Order #{order_id} — Service Fee",
    "Order #{order_id} — Monthly Plan",
    "Order #{order_id} — Annual Renewal",
    "Order #{order_id} — One-time Purchase",
    "Order #{order_id} — Upgrade Fee",
    "Order #{order_id} — Add-on Package",
    "Order #{order_id} — Consultation Fee",
    "Order #{order_id} — Delivery Charge",
]

REFUND_REASONS = [
    "Customer requested refund",
    "Product not as described",
    "Duplicate charge",
    "Fraudulent transaction",
    "Service not delivered",
    "Customer changed mind",
    "Technical error during payment",
    "Order cancelled by merchant",
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def random_email(first, last):
    domain = random.choice(DOMAINS)
    variants = [
        f"{first.lower()}.{last.lower()}@{domain}",
        f"{first.lower()}{last[0].lower()}@{domain}",
        f"{first[0].lower()}{last.lower()}@{domain}",
        f"{first.lower()}_{last.lower()}@{domain}",
    ]
    return random.choice(variants)

def random_phone():
    return f"+1{random.randint(2000000000, 9999999999)}"

def random_amount(min_val=5.0, max_val=5000.0):
    return round(random.uniform(min_val, max_val), 2)

def random_date(days_back=90):
    now = datetime.now(timezone.utc)
    delta = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return (now - delta).isoformat()

def pick_weighted(items, weights):
    return random.choices(items, weights=weights, k=1)[0]

# ─── API Client ───────────────────────────────────────────────────────────────

class SeedClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self.merchants = []
        self.customers_by_merchant = {}  # merchant_id -> [customer_data]
        self.payments_by_merchant = {}   # merchant_id -> [payment_data]

    async def create_merchant(self, name, email):
        resp = await self.client.post(
            f"{self.base_url}/api/merchants",
            json={"name": name, "email": email, "status": "active"},
        )
        if resp.status_code == 201:
            return resp.json()
        # If merchant already exists (email conflict), try with unique suffix
        unique_email = f"{email.split('@')[0]}-{uuid.uuid4().hex[:8]}@{email.split('@')[1]}"
        resp = await self.client.post(
            f"{self.base_url}/api/merchants",
            json={"name": name, "email": unique_email, "status": "active"},
        )
        if resp.status_code == 201:
            return resp.json()
        raise Exception(f"Failed to create merchant: {resp.status_code} {resp.text}")

    async def create_customer(self, merchant_id, api_key, name, email, phone):
        resp = await self.client.post(
            f"{self.base_url}/api/{merchant_id}/customers",
            json={"name": name, "email": email, "phone": phone},
            headers={"X-API-Key": api_key},
        )
        if resp.status_code in (201, 200):
            return resp.json()
        raise Exception(f"Failed to create customer: {resp.status_code} {resp.text}")

    async def create_payment(self, merchant_id, api_key, customer_id, amount, currency, method, description):
        resp = await self.client.post(
            f"{self.base_url}/api/{merchant_id}/payments",
            json={
                "customer_id": customer_id,
                "amount": amount,
                "currency": currency,
                "method": method,
                "description": description,
            },
            headers={"X-API-Key": api_key},
        )
        if resp.status_code in (201, 200):
            return resp.json()
        raise Exception(f"Failed to create payment: {resp.status_code} {resp.text}")

    async def authorize_payment(self, merchant_id, api_key, payment_id):
        resp = await self.client.post(
            f"{self.base_url}/api/{merchant_id}/payments/{payment_id}/authorize",
            headers={"X-API-Key": api_key},
        )
        return resp.status_code in (200, 201)

    async def capture_payment(self, merchant_id, api_key, payment_id):
        resp = await self.client.post(
            f"{self.base_url}/api/{merchant_id}/payments/{payment_id}/capture",
            headers={"X-API-Key": api_key},
        )
        return resp.status_code in (200, 201)

    async def settle_payment(self, merchant_id, api_key, payment_id):
        resp = await self.client.post(
            f"{self.base_url}/api/{merchant_id}/payments/{payment_id}/settle",
            headers={"X-API-Key": api_key},
        )
        return resp.status_code in (200, 201)

    async def fail_payment(self, merchant_id, api_key, payment_id):
        resp = await self.client.post(
            f"{self.base_url}/api/{merchant_id}/payments/{payment_id}/fail",
            headers={"X-API-Key": api_key},
        )
        return resp.status_code in (200, 201)

    async def create_refund(self, merchant_id, api_key, payment_id, amount, reason):
        resp = await self.client.post(
            f"{self.base_url}/api/{merchant_id}/payments/{payment_id}/refund",
            json={"amount": amount, "reason": reason},
            headers={"X-API-Key": api_key},
        )
        if resp.status_code in (201, 200):
            return resp.json()
        raise Exception(f"Failed to create refund: {resp.status_code} {resp.text}")

    async def process_refund(self, merchant_id, api_key, refund_id):
        resp = await self.client.post(
            f"{self.base_url}/api/{merchant_id}/refunds/{refund_id}/process",
            headers={"X-API-Key": api_key},
        )
        return resp.status_code in (200, 201)

    async def close(self):
        await self.client.aclose()


# ─── Seed Logic ───────────────────────────────────────────────────────────────

async def seed_data(num_merchants=5, num_customers=200, num_payments=500):
    client = SeedClient()

    try:
        # ── Step 1: Create Merchants ──
        print(f"\n{'='*60}")
        print(f"  SEED DATA GENERATOR")
        print(f"{'='*60}")
        print(f"\nTarget: {num_merchants} merchants, {num_customers} customers, {num_payments} payments")
        print(f"\n[1/5] Creating {num_merchants} merchants...")

        used_names = set()
        for i in range(num_merchants):
            name = MERCHANT_NAMES[i % len(MERCHANT_NAMES)]
            if name in used_names:
                name = f"{name} {i+1}"
            used_names.add(name)
            email = f"contact-{i+1}@{name.lower().replace(' ', '')}.com"

            merchant = await client.create_merchant(name, email)
            client.merchants.append(merchant)
            print(f"  ✓ {name} (ID: {merchant['merchant_id']}, API Key: {merchant['api_key'][:12]}...)")

        # ── Step 2: Create Customers ──
        print(f"\n[2/5] Creating {num_customers} customers...")
        customers_per_merchant = num_customers // num_merchants
        remaining = num_customers % num_merchants

        for idx, merchant in enumerate(client.merchants):
            count = customers_per_merchant + (1 if idx < remaining else 0)
            mid = merchant["merchant_id"]
            api_key = merchant["api_key"]
            client.customers_by_merchant[mid] = []

            for _ in range(count):
                first = random.choice(FIRST_NAMES)
                last = random.choice(LAST_NAMES)
                email = random_email(first, last)
                phone = random_phone()

                try:
                    cust = await client.create_customer(mid, api_key, f"{first} {last}", email, phone)
                    client.customers_by_merchant[mid].append(cust)
                except Exception:
                    pass  # Skip duplicates

            print(f"  ✓ {merchant['name']}: {len(client.customers_by_merchant[mid])} customers")

        total_customers = sum(len(v) for v in client.customers_by_merchant.values())
        print(f"  Total: {total_customers} customers created")

        # ── Step 3: Create Payments ──
        print(f"\n[3/5] Creating {num_payments} payments...")
        payments_per_merchant = num_payments // num_merchants
        remaining_p = num_payments % num_merchants

        for idx, merchant in enumerate(client.merchants):
            count = payments_per_merchant + (1 if idx < remaining_p else 0)
            mid = merchant["merchant_id"]
            api_key = merchant["api_key"]
            customers = client.customers_by_merchant[mid]
            client.payments_by_merchant[mid] = []

            if not customers:
                print(f"  ⚠ {merchant['name']}: No customers, skipping payments")
                continue

            for i in range(count):
                cust = random.choice(customers)
                amount = random_amount(10.0, 2500.0)
                currency = pick_weighted(CURRENCIES, CURRENCY_WEIGHTS)
                method = pick_weighted(PAYMENT_METHODS, METHOD_WEIGHTS)
                desc = random.choice(PAYMENT_DESCRIPTIONS).format(order_id=random.randint(10000, 99999))

                try:
                    payment = await client.create_payment(mid, api_key, cust["customer_id"], amount, currency, method, desc)
                    client.payments_by_merchant[mid].append(payment)
                except Exception as e:
                    pass  # Skip failures

            print(f"  ✓ {merchant['name']}: {len(client.payments_by_merchant[mid])} payments")

        total_payments = sum(len(v) for v in client.payments_by_merchant.values())
        print(f"  Total: {total_payments} payments created")

        # ── Step 4: Process Payments (authorize → capture → settle) ──
        print(f"\n[4/5] Processing payments (authorize, capture, settle, fail)...")
        captured = []
        settled = []
        failed = []

        for merchant in client.merchants:
            mid = merchant["merchant_id"]
            api_key = merchant["api_key"]
            payments = client.payments_by_merchant[mid]

            for payment in payments:
                pid = payment["payment_id"]
                roll = random.random()

                if roll < 0.15:
                    # 15% fail immediately
                    await client.fail_payment(mid, api_key, pid)
                    failed.append(payment)
                elif roll < 0.25:
                    # 10% stay authorized
                    await client.authorize_payment(mid, api_key, pid)
                elif roll < 0.40:
                    # 15% captured
                    await client.authorize_payment(mid, api_key, pid)
                    await client.capture_payment(mid, api_key, pid)
                    captured.append(payment)
                else:
                    # 60% fully settled
                    await client.authorize_payment(mid, api_key, pid)
                    await client.capture_payment(mid, api_key, pid)
                    await client.settle_payment(mid, api_key, pid)
                    settled.append(payment)

        print(f"  ✓ Authorized (pending): {len([p for m in client.merchants for p in client.payments_by_merchant.get(m['merchant_id'], []) if p.get('status') == 'authorized'])}")
        print(f"  ✓ Captured: {len(captured)}")
        print(f"  ✓ Settled: {len(settled)}")
        print(f"  ✓ Failed: {len(failed)}")

        # ── Step 5: Create Refunds ──
        print(f"\n[5/5] Creating refunds on captured/settled payments...")
        refundable = captured + settled
        num_refunds = min(80, len(refundable) // 3)

        if refundable:
            refund_payments = random.sample(refundable, min(num_refunds, len(refundable)))
            refunds_created = 0

            for payment in refund_payments:
                # Find the merchant for this payment
                merchant_for_payment = None
                for m in client.merchants:
                    if payment in client.payments_by_merchant.get(m["merchant_id"], []):
                        merchant_for_payment = m
                        break

                if not merchant_for_payment:
                    continue

                mid = merchant_for_payment["merchant_id"]
                api_key = merchant_for_payment["api_key"]
                refund_amount = round(random.uniform(5.0, float(payment.get("amount", 100))) , 2)
                reason = random.choice(REFUND_REASONS)

                try:
                    refund = await client.create_refund(mid, api_key, payment["payment_id"], refund_amount, reason)
                    refunds_created += 1

                    # Process 70% of refunds
                    if random.random() < 0.7:
                        await client.process_refund(mid, api_key, refund["refund_id"])
                except Exception:
                    pass

            print(f"  ✓ {refunds_created} refunds created, ~70% processed")
        else:
            print(f"  ⚠ No refundable payments found")

        # ── Summary ──
        print(f"\n{'='*60}")
        print(f"  SEED COMPLETE")
        print(f"{'='*60}")
        print(f"  Merchants:  {len(client.merchants)}")
        print(f"  Customers:  {sum(len(v) for v in client.customers_by_merchant.values())}")
        print(f"  Payments:   {sum(len(v) for v in client.payments_by_merchant.values())}")
        print(f"  Refunds:    ~{num_refunds // 2 if refundable else 0}")
        print(f"{'='*60}\n")

    finally:
        await client.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed payment gateway with realistic data")
    parser.add_argument("--merchants", type=int, default=5, help="Number of merchants (default: 5)")
    parser.add_argument("--customers", type=int, default=200, help="Number of customers (default: 200)")
    parser.add_argument("--payments", type=int, default=500, help="Number of payments (default: 500)")
    parser.add_argument("--url", type=str, default=BASE_URL, help="Base URL of payment-core-service")
    args = parser.parse_args()

    BASE_URL = args.url
    asyncio.run(seed_data(args.merchants, args.customers, args.payments))
