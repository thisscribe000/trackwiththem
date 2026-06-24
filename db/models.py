from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    packages: Mapped[list["TrackedPackage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class TrackedPackage(Base):
    __tablename__ = "tracked_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    tracking_number: Mapped[str] = mapped_column(String(255), nullable=False)
    carrier_code: Mapped[str] = mapped_column(String(50), nullable=False)
    carrier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    last_checkpoint_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checkpoint_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estimated_delivery: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    customs_warning_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped[User] = relationship(back_populates="packages")
    status_history: Mapped[list["StatusHistory"]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tracked_packages.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    package: Mapped[TrackedPackage] = relationship(back_populates="status_history")
