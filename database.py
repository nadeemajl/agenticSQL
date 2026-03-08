from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    ForeignKey,
    Text,
    Numeric,
    Enum,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import datetime

DATABASE_URL = "sqlite:///agentic_sql.db"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ------------------------------------------------------------------
# Branches
# ------------------------------------------------------------------
class Branch(Base):
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # relationships
    employees = relationship("Employee", back_populates="branch")
    accounts = relationship("Account", back_populates="branch")


# ------------------------------------------------------------------
# Addresses
# ------------------------------------------------------------------
class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    street = Column(String(255), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100))
    postal_code = Column(String(20))
    country = Column(String(100), nullable=False)

    # relationships
    customers = relationship("Customer", back_populates="address")
    phone_numbers = relationship("PhoneNumber", back_populates="address", cascade="all, delete-orphan")


# ------------------------------------------------------------------
# Phone Numbers  (each address can have multiple phone numbers)
# ------------------------------------------------------------------
class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=False)
    number = Column(String(30), nullable=False)
    label = Column(String(30), default="home")  # home, work, mobile, fax

    # relationships
    address = relationship("Address", back_populates="phone_numbers")


# ------------------------------------------------------------------
# Customers
# ------------------------------------------------------------------
class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(20))
    date_of_birth = Column(Date)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # relationships
    address = relationship("Address", back_populates="customers")
    accounts = relationship("Account", back_populates="customer")
    loans = relationship("Loan", back_populates="customer")


# ------------------------------------------------------------------
# Employees
# ------------------------------------------------------------------
class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(20))
    role = Column(String(100))
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    hire_date = Column(Date)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # relationships
    branch = relationship("Branch", back_populates="employees")
    managed_accounts = relationship("AccountManager", back_populates="employee")


# ------------------------------------------------------------------
# Account Managers  (join table: employee ↔ account)
# ------------------------------------------------------------------
class AccountManager(Base):
    __tablename__ = "account_managers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)

    # relationships
    employee = relationship("Employee", back_populates="managed_accounts")
    account = relationship("Account", back_populates="managers")


# ------------------------------------------------------------------
# Accounts
# ------------------------------------------------------------------
class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_number = Column(String(30), unique=True, nullable=False)
    account_type = Column(
        Enum("checking", "savings", "credit", "investment", name="account_type_enum"),
        nullable=False,
    )
    balance = Column(Numeric(18, 2), default=0.00)
    currency = Column(String(10), default="USD")
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    opened_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(
        Enum("active", "closed", "frozen", name="account_status_enum"), default="active"
    )

    # relationships
    customer = relationship("Customer", back_populates="accounts")
    branch = relationship("Branch", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")
    loans = relationship("Loan", back_populates="account")
    managers = relationship("AccountManager", back_populates="account")


# ------------------------------------------------------------------
# Transactions
# ------------------------------------------------------------------
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    transaction_type = Column(
        Enum("deposit", "withdrawal", "transfer", "payment", name="txn_type_enum"),
        nullable=False,
    )
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(10), default="USD")
    description = Column(Text)
    reference_number = Column(String(50), unique=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # relationships
    account = relationship("Account", back_populates="transactions")


# ------------------------------------------------------------------
# Loans
# ------------------------------------------------------------------
class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    loan_type = Column(
        Enum("personal", "mortgage", "auto", "business", name="loan_type_enum"),
        nullable=False,
    )
    principal = Column(Numeric(18, 2), nullable=False)
    interest_rate = Column(Float, nullable=False)  # annual percentage
    term_months = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(
        Enum("active", "paid_off", "defaulted", name="loan_status_enum"), default="active"
    )
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # relationships
    customer = relationship("Customer", back_populates="loans")
    account = relationship("Account", back_populates="loans")


# ------------------------------------------------------------------
# Create all tables
# ------------------------------------------------------------------
def init_db():
    Base.metadata.create_all(bind=engine)
    print("All tables created successfully.")


if __name__ == "__main__":
    init_db()
