from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


class System(Base):
    __tablename__ = "systems"

    id64: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    normalized_name: Mapped[str] = mapped_column(String(160), index=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    permit_required: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stations: Mapped[list["Station"]] = relationship(back_populates="system")

    __table_args__ = (Index("ix_system_coordinates", "x", "y", "z"),)


class Station(Base):
    __tablename__ = "stations"

    market_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    system_id64: Mapped[int] = mapped_column(ForeignKey("systems.id64"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    normalized_name: Mapped[str] = mapped_column(String(180), index=True)
    station_type: Mapped[str] = mapped_column(String(100), default="Unknown")
    distance_to_arrival_ls: Mapped[float] = mapped_column(Float, default=0)
    largest_pad: Mapped[str] = mapped_column(String(1), default="L")
    planetary: Mapped[bool] = mapped_column(Boolean, default=False)
    fleet_carrier: Mapped[bool] = mapped_column(Boolean, default=False)
    odyssey: Mapped[bool] = mapped_column(Boolean, default=False)
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    system: Mapped[System] = relationship(back_populates="stations")
    observations: Mapped[list["MarketObservation"]] = relationship(back_populates="station")

    __table_args__ = (
        Index("ix_station_filters", "largest_pad", "planetary", "fleet_carrier", "odyssey"),
    )


class Commodity(Base):
    __tablename__ = "commodities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(140), unique=True)
    display_name: Mapped[str] = mapped_column(String(140))
    category: Mapped[str] = mapped_column(String(100), default="Unknown")
    observations: Mapped[list["MarketObservation"]] = relationship(back_populates="commodity")


class MarketObservation(Base):
    __tablename__ = "market_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("stations.market_id"), index=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), index=True)
    buy_price: Mapped[int] = mapped_column(Integer, default=0)
    sell_price: Mapped[int] = mapped_column(Integer, default=0)
    supply: Mapped[int] = mapped_column(Integer, default=0)
    demand: Mapped[int] = mapped_column(Integer, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    station: Mapped[Station] = relationship(back_populates="observations")
    commodity: Mapped[Commodity] = relationship(back_populates="observations")

    __table_args__ = (
        UniqueConstraint("market_id", "commodity_id", name="uq_market_commodity"),
        Index("ix_market_buy", "commodity_id", "buy_price"),
        Index("ix_market_sell", "commodity_id", "sell_price"),
    )


class ShipProfile(Base):
    __tablename__ = "ship_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    ship_model: Mapped[str] = mapped_column(String(100))
    cargo_capacity: Mapped[int] = mapped_column(Integer)
    unladen_jump_range: Mapped[float] = mapped_column(Float)
    laden_jump_range: Mapped[float] = mapped_column(Float)
    pad_size: Mapped[str] = mapped_column(String(1))
    has_fuel_scoop: Mapped[bool] = mapped_column(Boolean, default=False)
    shielded: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    values: Mapped[dict] = mapped_column(JSON)


class DataImport(Base):
    __tablename__ = "data_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str] = mapped_column(Text)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    progress: Mapped[float] = mapped_column(Float, default=0)
    records: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    progress: Mapped[float] = mapped_column(Float, default=0)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


settings = get_settings()
connect_args = (
    {"check_same_thread": False, "timeout": 60}
    if settings.database_url.startswith("sqlite")
    else {}
)
engine = create_engine(settings.database_url, connect_args=connect_args)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_database() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        recover_interrupted_jobs(session)


def recover_interrupted_jobs(session: Session) -> int:
    """Jobs use daemon threads, so queued/running rows cannot survive a restart."""
    now = datetime.now(UTC)
    result = session.execute(
        update(Job)
        .where(Job.status.in_(("queued", "running")))
        .values(
            status="failed",
            error="Interrupted when Elite Logistics last stopped. Start the operation again.",
            updated_at=now,
        )
    )
    session.commit()
    return int(result.rowcount or 0)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
