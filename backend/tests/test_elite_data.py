from pathlib import Path

from sqlalchemy import func, select

from datetime import UTC, datetime
import json

from elite_logistics.database import Job, MarketObservation, recover_interrupted_jobs
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


def test_idle_journal_stays_live_while_elite_process_is_running(tmp_path, monkeypatch):
    journal = tmp_path / "Journal.2020-01-01T000000.01.log"
    journal.write_text(
        json.dumps(
            {
                "timestamp": "2020-01-01T00:00:00Z",
                "event": "Location",
                "StarSystem": "Sol",
                "SystemAddress": 10477373803,
                "Docked": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "elite_logistics.elite_data._elite_game_process_running", lambda: True
    )

    state = EliteDataReader(tmp_path).read()

    assert state.available is True
    assert state.game_running is True
    assert not any("not currently detected" in warning for warning in state.warnings)


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


def test_interrupted_jobs_are_failed_on_restart(session):
    now = datetime.now(UTC)
    session.add(Job(id="stale-import", kind="spansh_import", status="running", progress=0.2, created_at=now, updated_at=now))
    session.commit()

    assert recover_interrupted_jobs(session) == 1
    job = session.get(Job, "stale-import")
    assert job is not None
    assert job.status == "failed"
    assert "Start the operation again" in (job.error or "")
