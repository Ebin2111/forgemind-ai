"""SQLAlchemy 2.0 ORM models: equipment registry, maintenance work orders, indexed documents."""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# Allowed values. Mirrored by the Literal types in schemas.py and enforced in the database.
EQUIPMENT_STATUSES = ("operational", "maintenance", "fault", "retired")
PRIORITIES = ("low", "medium", "high", "critical")
WORK_ORDER_STATUSES = ("open", "in_progress", "closed")
ROLES = ("admin", "technician")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint(_in_list("status", EQUIPMENT_STATUSES), name="status_valid"),
        Index("ix_equipment_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag: Mapped[str] = mapped_column(String(50), unique=True, index=True, comment="Asset tag, e.g. CNC-101")
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(200))
    manufacturer: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(30), default="operational")

    work_orders: Mapped[list["WorkOrder"]] = relationship(
        back_populates="equipment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkOrder.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<Equipment {self.tag} ({self.status})>"


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint(_in_list("priority", PRIORITIES), name="priority_valid"),
        CheckConstraint(_in_list("status", WORK_ORDER_STATUSES), name="status_valid"),
        CheckConstraint("downtime_hours >= 0", name="downtime_non_negative"),
        Index("ix_work_orders_status", "status"),
        Index("ix_work_orders_priority", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wo_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="open")
    technician: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[date] = mapped_column(Date, default=date.today, index=True, comment="Date the work order was raised")
    downtime_hours: Mapped[float] = mapped_column(Float, default=0.0)

    equipment: Mapped[Equipment] = relationship(back_populates="work_orders")

    def __repr__(self) -> str:
        return f"<WorkOrder {self.wo_number} {self.status}/{self.priority}>"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("pages >= 0 AND chunks >= 0", name="counts_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(300), unique=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<Document {self.filename} pages={self.pages} chunks={self.chunks}>"


class User(Base):
    """A person who can sign in. Passwords are stored only as salted scrypt hashes."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in_list("role", ROLES), name="role_valid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, comment="Always stored in lower case")
    name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(20), default="technician")
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<User {self.email} {self.role}>"