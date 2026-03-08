"""
loyalty_database.py
===================
SQLAlchemy models for the loyalty points system database (loyalty.db).

Tables:
  - customers     : mirrors key fields from agentic_sql.db customers (linked by customer_id)
  - loyalty_points: earned point events per customer
  - rewards       : rewards redeemed by customers

The 'customer_id' column in loyalty customers references the ID in the
main agentic_sql.db customers table (cross-database logical foreign key —
enforced at application level since SQLite cannot cross-file FK).
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Text,
    DateTime,
    ForeignKey,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import datetime

LOYALTY_DB_URL = "sqlite:///loyalty.db"

engine = create_engine(LOYALTY_DB_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ------------------------------------------------------------------
# Customers (mirror of key fields from agentic_sql.db)
# customer_id links back to agentic_sql.db customers.id
# ------------------------------------------------------------------
class LoyaltyCustomer(Base):
    __tablename__ = "customers"

    customer_id = Column(Integer, primary_key=True)  # same ID as agentic_sql.db
    name = Column(String(200), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    phone_number = Column(String(30))

    # relationships
    loyalty_points = relationship(
        "LoyaltyPoint", back_populates="customer", cascade="all, delete-orphan"
    )
    rewards = relationship(
        "Reward", back_populates="customer", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<LoyaltyCustomer id={self.customer_id} name={self.name!r}>"


# ------------------------------------------------------------------
# Loyalty Points
# ------------------------------------------------------------------
class LoyaltyPoint(Base):
    __tablename__ = "loyalty_points"

    point_id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"), nullable=False)
    points = Column(Integer, nullable=False)
    date_earned = Column(Date, nullable=False)

    # relationship
    customer = relationship("LoyaltyCustomer", back_populates="loyalty_points")

    def __repr__(self):
        return f"<LoyaltyPoint id={self.point_id} customer={self.customer_id} pts={self.points}>"


# ------------------------------------------------------------------
# Rewards
# ------------------------------------------------------------------
class Reward(Base):
    __tablename__ = "rewards"

    reward_id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"), nullable=False)
    reward_name = Column(String(150), nullable=False)
    reward_description = Column(Text)
    date_rewarded = Column(Date, nullable=False)

    # relationship
    customer = relationship("LoyaltyCustomer", back_populates="rewards")

    def __repr__(self):
        return f"<Reward id={self.reward_id} customer={self.customer_id} name={self.reward_name!r}>"


# ------------------------------------------------------------------
# Create all tables
# ------------------------------------------------------------------
def init_loyalty_db():
    Base.metadata.create_all(bind=engine)
    print("Loyalty DB tables created successfully.")


if __name__ == "__main__":
    init_loyalty_db()
