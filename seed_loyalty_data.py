"""
seed_loyalty_data.py
====================
Generates realistic synthetic data for the loyalty.db database.

Data volume:
  - All 500 customers from agentic_sql.db are registered in the loyalty system
  - Each customer earns between 5–25 loyalty point events
  - ~60% of customers have redeemed at least one reward
  - Total points per event: 10–500 (weighted towards smaller values)
  - Date range: 2022-01-01 to 2026-03-01

The customer_id values match exactly those in agentic_sql.db (1-500).
"""

import random
import datetime
import sqlite3

from sqlalchemy.orm import Session

from loyalty_database import (
    engine,
    init_loyalty_db,
    LoyaltyCustomer,
    LoyaltyPoint,
    Reward,
)

# ── Seed for reproducibility ───────────────────────────────────────────────
random.seed(99)

# ── Configuration ──────────────────────────────────────────────────────────
MIN_POINT_EVENTS = 5
MAX_POINT_EVENTS = 25
REWARD_PROBABILITY = 0.60          # 60% of customers have at least 1 reward
MAX_REWARDS_PER_CUSTOMER = 5
START_DATE = datetime.date(2022, 1, 1)
END_DATE = datetime.date(2026, 3, 1)

# Reward catalogue
REWARD_CATALOG = [
    ("Free Monthly Account Fee Waiver", "One month waiver of the monthly account maintenance fee."),
    ("$10 Cashback Bonus", "Receive $10 cashback credited directly to your account."),
    ("0% Foreign Transaction Fee", "Enjoy zero foreign transaction fees for 3 months."),
    ("Priority Customer Service", "Access to dedicated priority customer service line for 6 months."),
    ("Travel Insurance Upgrade", "Complimentary travel insurance upgrade for your next trip."),
    ("Bonus Interest Rate", "0.5% bonus interest rate on savings account for 3 months."),
    ("Loan Rate Discount", "0.25% discount on your next personal loan interest rate."),
    ("Gift Voucher $25", "$25 gift voucher redeemable at partner retail stores."),
    ("Movie Tickets x2", "Two complimentary movie tickets at participating cinemas."),
    ("Airport Lounge Access", "Single complimentary visit to partner airport lounges."),
    ("Free Cheque Book", "One complimentary cheque book (50 leaves)."),
    ("Investment Consultation", "Free 30-minute consultation with an investment advisor."),
    ("Merchant Discount 15%", "15% discount at participating merchant partners for 1 month."),
    ("Overdraft Fee Waiver", "One-time waiver of overdraft fee up to $35."),
    ("Annual Fee Waiver", "Annual credit card fee waived for the next year."),
]


def random_date(start: datetime.date, end: datetime.date) -> datetime.date:
    delta = (end - start).days
    return start + datetime.timedelta(days=random.randint(0, delta))


def load_customers_from_agentic_sql() -> list[dict]:
    """Read all customers from the main agentic_sql.db."""
    conn = sqlite3.connect("agentic_sql.db")
    cur = conn.cursor()
    cur.execute("SELECT id, first_name, last_name, email, phone FROM customers ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "customer_id": row[0],
            "name": f"{row[1]} {row[2]}",
            "email": row[3],
            "phone": row[4] or "",
        }
        for row in rows
    ]


def seed_loyalty_data():
    print("Initializing loyalty database schema...")
    init_loyalty_db()

    print("Loading customers from agentic_sql.db...")
    source_customers = load_customers_from_agentic_sql()
    print(f"  Found {len(source_customers)} customers to import.")

    print("Seeding loyalty data...")

    loyalty_customers = []
    loyalty_points = []
    rewards = []

    for cust in source_customers:
        # 1. Create loyalty customer record
        loyalty_customers.append(
            LoyaltyCustomer(
                customer_id=cust["customer_id"],
                name=cust["name"],
                email=cust["email"],
                phone_number=cust["phone"],
            )
        )

        # 2. Generate loyalty point events
        num_events = random.randint(MIN_POINT_EVENTS, MAX_POINT_EVENTS)
        point_dates = sorted(
            [random_date(START_DATE, END_DATE) for _ in range(num_events)]
        )
        for earned_date in point_dates:
            # Points weighted towards smaller amounts (most common: 10-100)
            pts = random.choices(
                population=[10, 25, 50, 75, 100, 150, 200, 300, 500],
                weights=   [30, 25, 20, 10,  7,   4,   2,   1,   1],
                k=1
            )[0]
            loyalty_points.append(
                LoyaltyPoint(
                    customer_id=cust["customer_id"],
                    points=pts,
                    date_earned=earned_date,
                )
            )

        # 3. Maybe generate rewards
        if random.random() < REWARD_PROBABILITY:
            num_rewards = random.randint(1, MAX_REWARDS_PER_CUSTOMER)
            reward_dates = sorted(
                [random_date(START_DATE, END_DATE) for _ in range(num_rewards)]
            )
            for reward_date in reward_dates:
                reward_name, reward_desc = random.choice(REWARD_CATALOG)
                rewards.append(
                    Reward(
                        customer_id=cust["customer_id"],
                        reward_name=reward_name,
                        reward_description=reward_desc,
                        date_rewarded=reward_date,
                    )
                )

    # Bulk insert
    print(f"  Inserting {len(loyalty_customers)} customers...")
    print(f"  Inserting {len(loyalty_points)} loyalty point events...")
    print(f"  Inserting {len(rewards)} reward records...")

    with Session(engine) as session:
        session.bulk_save_objects(loyalty_customers)
        session.bulk_save_objects(loyalty_points)
        session.bulk_save_objects(rewards)
        session.commit()

    print("\n✅ Loyalty database seeded successfully!")
    print(f"   Customers:      {len(loyalty_customers):>6,}")
    print(f"   Point events:   {len(loyalty_points):>6,}")
    print(f"   Rewards:        {len(rewards):>6,}")


if __name__ == "__main__":
    seed_loyalty_data()
