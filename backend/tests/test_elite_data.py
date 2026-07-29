from pathlib import Path

from sqlalchemy import func, select

from elite_logistics.database import MarketObservation
from elite_logistics.elite_data import EliteDataReader, sync_current_market


FIXTURE = Path(__file__).parent / "fixtures" / "elite_reference"


def test_elite_reader_builds_current_state():
    state = EliteDataReader(FIXTURE).read()

    assert state.available is True
    assert state.commander == "Test Pilot"
    assert state.system_id64 == 1002
    assert state.station_market_id == 502
    assert state.docked is True
    assert state.phase == "docked"
    assert state.ship_name == "Wayfarer"
    assert state.cargo_capacity == 104
    assert state.cargo_count == 64
    assert state.target_system_id64 == 1002
    assert state.landing_pad == 14
    assert len(state.nav_route) == 2
    assert state.transactions[-1]["kind"] == "buy"


def test_current_market_is_normalized_and_idempotent(session):
    state = EliteDataReader(FIXTURE).read()

    assert sync_current_market(session, FIXTURE, state) == 1
    assert session.scalar(select(func.count()).select_from(MarketObservation)) == 9
    observation = session.scalar(
        select(MarketObservation).where(MarketObservation.market_id == 502)
    )
    assert observation is not None
    assert observation.provider == "EliteJournal"
    assert observation.supply == 5000
    assert sync_current_market(session, FIXTURE, state) == 0
    assert session.scalar(select(func.count()).select_from(MarketObservation)) == 9
