from pathlib import Path

from sqlalchemy import func, select

from elite_logistics.database import MarketObservation, Station, System
from elite_logistics.providers import SpanshDumpProvider


def test_tiny_pack_imports_normalized_current_state(session):
    assert session.scalar(select(func.count()).select_from(System)) == 4
    assert session.scalar(select(func.count()).select_from(Station)) == 4
    assert session.scalar(select(func.count()).select_from(MarketObservation)) == 8


def test_duplicate_import_does_not_duplicate_prices(session):
    path = Path(__file__).parent / "fixtures" / "tiny_spansh.json"
    SpanshDumpProvider(session).import_file(path, "fixture")
    assert session.scalar(select(func.count()).select_from(MarketObservation)) == 8

