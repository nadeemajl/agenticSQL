"""
seed_data.py
============
Generates realistic synthetic banking data and inserts it into the SQLite database.

Scale:
  - 5 branches, each with 25 employees
  - 500 customers, each with 4 addresses, each address with 4 phone numbers
  - Each customer has 1–3 accounts
  - Each customer has ~1200 transactions spread across their accounts
  - Loans seeded for ~40 % of customers
"""

import random
import uuid
import datetime
from decimal import Decimal

from faker import Faker
from sqlalchemy.orm import Session

from database import (
    engine,
    Base,
    Branch,
    Address,
    PhoneNumber,
    Customer,
    Employee,
    Account,
    AccountManager,
    Transaction,
    Loan,
    init_db,
)

fake = Faker("en_US")
random.seed(42)
Faker.seed(42)

# ── constants ──────────────────────────────────────────────────────────────────
NUM_BRANCHES = 5
EMPLOYEES_PER_BRANCH = 25
NUM_CUSTOMERS = 500
ADDRESSES_PER_CUSTOMER = 4
PHONES_PER_ADDRESS = 4
TARGET_TXN_PER_CUSTOMER = 1200
LOAN_PROBABILITY = 0.40

ACCOUNT_TYPES = ["checking", "savings", "credit", "investment"]
LOAN_TYPES = ["personal", "mortgage", "auto", "business"]
PHONE_LABELS = ["home", "work", "mobile", "fax"]
TXN_TYPES = ["deposit", "withdrawal", "transfer", "payment"]

# Realistic transaction description templates per type
TXN_DESCRIPTIONS = {
    "deposit": [
        "Payroll deposit – {employer}",
        "ACH transfer from {bank}",
        "Mobile check deposit",
        "Cash deposit at branch",
        "Direct deposit – {employer}",
        "Wire transfer received",
        "Dividend payment",
        "Tax refund deposit",
        "Rental income deposit",
        "Freelance payment received",
    ],
    "withdrawal": [
        "ATM withdrawal – {location}",
        "Cash withdrawal at branch",
        "POS purchase – {merchant}",
        "Online purchase – {merchant}",
        "Bill payment – {utility}",
        "Subscription – {service}",
        "Grocery purchase – {merchant}",
        "Fuel purchase – {merchant}",
        "Restaurant – {merchant}",
        "Pharmacy – {merchant}",
    ],
    "transfer": [
        "Internal transfer to account {acct}",
        "Wire transfer to {bank}",
        "Zelle transfer to {name}",
        "ACH transfer to {bank}",
        "Bill pay transfer – {utility}",
        "Savings sweep transfer",
        "Investment transfer",
        "Loan payment transfer",
    ],
    "payment": [
        "Mortgage payment",
        "Auto loan payment",
        "Credit card payment – {bank}",
        "Personal loan payment",
        "Utility bill – {utility}",
        "Insurance premium – {insurer}",
        "Rent payment",
        "Student loan payment",
        "Medical bill payment",
        "HOA fee payment",
    ],
}

EMPLOYERS = [
    "Acme Corp", "TechNova Inc", "Global Finance Ltd", "Metro Hospital",
    "City School District", "Sunrise Retail", "BlueSky Airlines", "GreenLeaf Foods",
    "Pinnacle Consulting", "Horizon Manufacturing",
]
BANKS = [
    "Chase", "Bank of America", "Wells Fargo", "Citibank", "US Bank",
    "TD Bank", "PNC Bank", "Capital One", "Regions Bank", "SunTrust",
]
MERCHANTS = [
    "Walmart", "Target", "Amazon", "Costco", "Kroger", "Walgreens",
    "Home Depot", "Best Buy", "Starbucks", "McDonald's", "Shell", "BP",
    "Whole Foods", "CVS", "Dollar General",
]
UTILITIES = [
    "AT&T", "Verizon", "Comcast", "Duke Energy", "Con Edison",
    "Pacific Gas & Electric", "American Water", "National Grid",
]
SERVICES = [
    "Netflix", "Spotify", "Amazon Prime", "Hulu", "Disney+",
    "Apple iCloud", "Google One", "Adobe Creative Cloud",
]
INSURERS = [
    "State Farm", "Allstate", "Geico", "Progressive", "USAA",
    "Nationwide", "Travelers", "Liberty Mutual",
]
LOCATIONS = [
    "Downtown ATM", "Airport Terminal", "Mall Kiosk", "Branch Lobby",
    "Gas Station ATM", "Grocery Store ATM",
]


def _txn_description(txn_type: str, customer_name: str = "") -> str:
    template = random.choice(TXN_DESCRIPTIONS[txn_type])
    return template.format(
        employer=random.choice(EMPLOYERS),
        bank=random.choice(BANKS),
        merchant=random.choice(MERCHANTS),
        utility=random.choice(UTILITIES),
        service=random.choice(SERVICES),
        insurer=random.choice(INSURERS),
        location=random.choice(LOCATIONS),
        acct=fake.numerify("####"),
        name=fake.name(),
    )


def _random_amount(txn_type: str) -> Decimal:
    """Return a realistic transaction amount for the given type."""
    if txn_type == "deposit":
        # Payroll / large deposits
        return Decimal(str(round(random.uniform(200, 8000), 2)))
    elif txn_type == "withdrawal":
        return Decimal(str(round(random.uniform(5, 1500), 2)))
    elif txn_type == "transfer":
        return Decimal(str(round(random.uniform(50, 5000), 2)))
    else:  # payment
        return Decimal(str(round(random.uniform(20, 3000), 2)))


def _random_date_between(start: datetime.date, end: datetime.date) -> datetime.datetime:
    delta = (end - start).days
    random_days = random.randint(0, max(delta, 0))
    random_seconds = random.randint(0, 86399)
    return datetime.datetime.combine(start, datetime.time()) + datetime.timedelta(
        days=random_days, seconds=random_seconds
    )


# ── seeding functions ──────────────────────────────────────────────────────────

def seed_branches(session: Session) -> list[Branch]:
    print("Seeding branches…")
    branch_names = [
        "Downtown Branch", "Westside Branch", "Northgate Branch",
        "Eastview Branch", "Southpark Branch",
    ]
    branches = []
    for name in branch_names:
        b = Branch(
            name=name,
            phone=fake.phone_number(),
            email=fake.company_email(),
        )
        session.add(b)
        branches.append(b)
    session.flush()
    return branches


def seed_employees(session: Session, branches: list[Branch]) -> list[Employee]:
    print("Seeding employees…")
    roles = [
        "Teller", "Loan Officer", "Branch Manager", "Financial Advisor",
        "Customer Service Rep", "Compliance Officer", "IT Support",
    ]
    employees = []
    for branch in branches:
        for _ in range(EMPLOYEES_PER_BRANCH):
            e = Employee(
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                email=fake.unique.email(),
                phone=fake.phone_number(),
                role=random.choice(roles),
                branch_id=branch.id,
                hire_date=fake.date_between(start_date="-10y", end_date="today"),
            )
            session.add(e)
            employees.append(e)
    session.flush()
    return employees


def seed_addresses_and_phones(session: Session) -> list[Address]:
    """Create a pool of addresses (4 per customer × 500 = 2000 total)."""
    print("Seeding addresses and phone numbers…")
    addresses = []
    total = NUM_CUSTOMERS * ADDRESSES_PER_CUSTOMER
    for _ in range(total):
        addr = Address(
            street=fake.street_address(),
            city=fake.city(),
            state=fake.state(),
            postal_code=fake.postcode(),
            country="United States",
        )
        session.add(addr)
        session.flush()  # get id
        for label in PHONE_LABELS:
            ph = PhoneNumber(
                address_id=addr.id,
                number=fake.phone_number(),
                label=label,
            )
            session.add(ph)
        addresses.append(addr)
    session.flush()
    return addresses


def seed_customers(session: Session, addresses: list[Address]) -> list[Customer]:
    print("Seeding customers…")
    customers = []
    addr_iter = iter(addresses)
    for _ in range(NUM_CUSTOMERS):
        # primary address is the first of the 4 assigned addresses
        primary_addr = next(addr_iter)
        # consume the remaining 3 addresses (they exist in DB but aren't FK'd to customer)
        for _ in range(ADDRESSES_PER_CUSTOMER - 1):
            next(addr_iter)
        c = Customer(
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            email=fake.unique.email(),
            phone=fake.phone_number(),
            date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=80),
            address_id=primary_addr.id,
        )
        session.add(c)
        customers.append(c)
    session.flush()
    return customers


def seed_accounts(
    session: Session, customers: list[Customer], branches: list[Branch]
) -> list[Account]:
    print("Seeding accounts…")
    accounts = []
    for customer in customers:
        num_accounts = random.randint(1, 3)
        chosen_types = random.sample(ACCOUNT_TYPES, k=min(num_accounts, len(ACCOUNT_TYPES)))
        for acct_type in chosen_types:
            acct = Account(
                account_number=fake.unique.numerify("##########"),
                account_type=acct_type,
                balance=Decimal(str(round(random.uniform(100, 50000), 2))),
                currency="USD",
                customer_id=customer.id,
                branch_id=random.choice(branches).id,
                status="active",
            )
            session.add(acct)
            accounts.append(acct)
    session.flush()
    return accounts


def seed_account_managers(
    session: Session, accounts: list[Account], employees: list[Employee]
) -> None:
    print("Seeding account managers…")
    for acct in accounts:
        # assign 1–2 managers per account
        managers = random.sample(employees, k=random.randint(1, 2))
        for emp in managers:
            am = AccountManager(
                employee_id=emp.id,
                account_id=acct.id,
            )
            session.add(am)
    session.flush()


def seed_transactions(
    session: Session, customers: list[Customer], accounts: list[Account]
) -> None:
    print(f"Seeding transactions (~{TARGET_TXN_PER_CUSTOMER} per customer)…")

    # Build a map: customer_id → list of accounts
    customer_accounts: dict[int, list[Account]] = {}
    for acct in accounts:
        customer_accounts.setdefault(acct.customer_id, []).append(acct)

    start_date = datetime.date.today() - datetime.timedelta(days=5 * 365)
    end_date = datetime.date.today()

    batch = []
    BATCH_SIZE = 5000

    for idx, customer in enumerate(customers):
        if (idx + 1) % 50 == 0:
            print(f"  … customer {idx + 1}/{NUM_CUSTOMERS}")

        cust_accounts = customer_accounts.get(customer.id, [])
        if not cust_accounts:
            continue

        # Distribute ~1200 transactions across the customer's accounts
        num_txns = random.randint(1150, 1250)
        running_balance: dict[int, Decimal] = {a.id: a.balance for a in cust_accounts}

        for _ in range(num_txns):
            acct = random.choice(cust_accounts)
            txn_type = random.choices(
                TXN_TYPES,
                weights=[35, 40, 15, 10],  # deposits, withdrawals most common
                k=1,
            )[0]
            amount = _random_amount(txn_type)
            txn_date = _random_date_between(start_date, end_date)

            # Update running balance (keep it non-negative for realism)
            if txn_type in ("withdrawal", "payment", "transfer"):
                if running_balance[acct.id] < amount:
                    txn_type = "deposit"  # flip to deposit to avoid overdraft
                    amount = _random_amount("deposit")
                else:
                    running_balance[acct.id] -= amount
            else:
                running_balance[acct.id] += amount

            txn = Transaction(
                account_id=acct.id,
                transaction_type=txn_type,
                amount=amount,
                currency="USD",
                description=_txn_description(txn_type),
                reference_number=str(uuid.uuid4()).replace("-", "")[:20],
                created_at=txn_date,
            )
            batch.append(txn)

            if len(batch) >= BATCH_SIZE:
                session.bulk_save_objects(batch)
                session.flush()
                batch.clear()

        # Sync final balances back to accounts
        for acct in cust_accounts:
            acct.balance = running_balance[acct.id]

    if batch:
        session.bulk_save_objects(batch)
        session.flush()


def seed_loans(
    session: Session, customers: list[Customer], accounts: list[Account]
) -> None:
    print("Seeding loans…")
    customer_accounts: dict[int, list[Account]] = {}
    for acct in accounts:
        customer_accounts.setdefault(acct.customer_id, []).append(acct)

    for customer in customers:
        if random.random() > LOAN_PROBABILITY:
            continue
        num_loans = random.randint(1, 2)
        for _ in range(num_loans):
            loan_type = random.choice(LOAN_TYPES)
            if loan_type == "mortgage":
                principal = Decimal(str(round(random.uniform(80000, 600000), 2)))
                rate = round(random.uniform(3.0, 7.5), 2)
                term = random.choice([120, 180, 240, 360])
            elif loan_type == "auto":
                principal = Decimal(str(round(random.uniform(5000, 60000), 2)))
                rate = round(random.uniform(3.5, 9.0), 2)
                term = random.choice([24, 36, 48, 60, 72])
            elif loan_type == "personal":
                principal = Decimal(str(round(random.uniform(1000, 30000), 2)))
                rate = round(random.uniform(6.0, 24.0), 2)
                term = random.choice([12, 24, 36, 48, 60])
            else:  # business
                principal = Decimal(str(round(random.uniform(10000, 500000), 2)))
                rate = round(random.uniform(4.0, 12.0), 2)
                term = random.choice([12, 24, 36, 60, 84, 120])

            start_date = fake.date_between(start_date="-8y", end_date="-1y")
            end_date = start_date + datetime.timedelta(days=term * 30)
            status = (
                "paid_off"
                if end_date < datetime.date.today()
                else random.choices(["active", "defaulted"], weights=[90, 10])[0]
            )

            cust_accts = customer_accounts.get(customer.id, [])
            linked_acct = random.choice(cust_accts).id if cust_accts else None

            loan = Loan(
                customer_id=customer.id,
                account_id=linked_acct,
                loan_type=loan_type,
                principal=principal,
                interest_rate=rate,
                term_months=term,
                start_date=start_date,
                end_date=end_date,
                status=status,
            )
            session.add(loan)
    session.flush()


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    print("Initialising database schema…")
    # Drop and recreate to start fresh
    Base.metadata.drop_all(bind=engine)
    init_db()

    with Session(engine) as session:
        with session.begin():
            branches = seed_branches(session)
            employees = seed_employees(session, branches)
            addresses = seed_addresses_and_phones(session)
            customers = seed_customers(session, addresses)
            accounts = seed_accounts(session, customers, branches)
            seed_account_managers(session, accounts, employees)
            seed_transactions(session, customers, accounts)
            seed_loans(session, customers, accounts)

    print("\n✅  Seeding complete!")
    print(f"   Branches   : {NUM_BRANCHES}")
    print(f"   Employees  : {NUM_BRANCHES * EMPLOYEES_PER_BRANCH}")
    print(f"   Customers  : {NUM_CUSTOMERS}")
    print(f"   Addresses  : {NUM_CUSTOMERS * ADDRESSES_PER_CUSTOMER}")
    print(f"   Phone #s   : {NUM_CUSTOMERS * ADDRESSES_PER_CUSTOMER * PHONES_PER_ADDRESS}")
    print(f"   Accounts   : ~{NUM_CUSTOMERS * 2} (avg 2 per customer)")
    print(f"   Transactions: ~{NUM_CUSTOMERS * TARGET_TXN_PER_CUSTOMER:,}")


if __name__ == "__main__":
    main()
