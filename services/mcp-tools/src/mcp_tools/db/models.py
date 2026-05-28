"""SQLAlchemy models for MCP Tools database."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Store(Base):
    """Store model representing a shop in the mall."""

    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    opening_hours: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    # JSON type works with both PostgreSQL and SQLite
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)

    routes: Mapped[list["Route"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Store(id={self.id!r}, name={self.name!r})>"


class Route(Base):
    """Route model representing navigation path to a store."""

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("stores.id"), nullable=False
    )
    from_location: Mapped[str] = mapped_column(String(50), default="kiosk")

    store: Mapped["Store"] = relationship(back_populates="routes")
    steps: Mapped[list["RouteStep"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="RouteStep.order",
    )

    def __repr__(self) -> str:
        return f"<Route(id={self.id}, store_id={self.store_id!r}, from={self.from_location!r})>"


class RouteStep(Base):
    """RouteStep model representing a single step in a navigation route."""

    __tablename__ = "route_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routes.id"), nullable=False
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(String(200), nullable=False)
    landmark: Mapped[Optional[str]] = mapped_column(String(100))
    distance_meters: Mapped[Optional[int]] = mapped_column(Integer)

    route: Mapped["Route"] = relationship(back_populates="steps")

    def __repr__(self) -> str:
        return f"<RouteStep(order={self.order}, instruction={self.instruction!r})>"


class EventLog(Base):
    """EventLog model for session event logging."""

    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # JSON type works with both PostgreSQL and SQLite
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<EventLog(session={self.session_id!r}, type={self.event_type!r})>"
