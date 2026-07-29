import json
from pathlib import Path

from elite_logistics.elite_adapter import read_elite_state


def write_journal(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_reads_latest_elite_state_and_reconciles_session_balance(tmp_path: Path):
    write_journal(
        tmp_path / "Journal.2026-07-28T120000.01.log",
        [
            {"timestamp": "2026-07-28T12:00:00Z", "event": "Fileheader"},
            {
                "timestamp": "2026-07-28T12:00:01Z",
                "event": "LoadGame",
                "Commander": "Test Commander",
                "Ship": "Type6",
                "Ship_Localised": "Type-6 Transporter",
                "Credits": 1_000_000,
            },
            {
                "timestamp": "2026-07-28T12:00:02Z",
                "event": "Loadout",
                "Ship": "Type6",
                "CargoCapacity": 104,
                "MaxJumpRange": 18.7,
                "Rebuy": 50_000,
            },
            {
                "timestamp": "2026-07-28T12:00:03Z",
                "event": "Location",
                "StarSystem": "Test System",
                "SystemAddress": 123456,
                "Docked": True,
                "StationName": "Test Port",
                "MarketID": 987654,
            },
            {
                "timestamp": "2026-07-28T12:00:04Z",
                "event": "MarketBuy",
                "TotalCost": 100_000,
            },
            {
                "timestamp": "2026-07-28T12:00:05Z",
                "event": "MarketSell",
                "TotalSale": 150_000,
            },
        ],
    )
    (tmp_path / "Cargo.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-07-28T12:00:06Z",
                "event": "Cargo",
                "Count": 12,
                "Inventory": [
                    {"Name": "gold", "Name_Localised": "Gold", "Count": 12, "Stolen": 0}
                ],
            }
        ),
        encoding="utf-8",
    )

    state = read_elite_state(tmp_path)

    assert state.available is True
    assert state.commander == "Test Commander"
    assert state.system_id64 == 123456
    assert state.station_market_id == 987654
    assert state.cargo_capacity == 104
    assert state.max_jump_range == 18.7
    assert state.pad_size == "M"
    assert state.credits == 1_050_000
    assert state.rebuy == 50_000
    assert state.cargo_count == 12
    assert state.cargo[0].name == "Gold"


def test_missing_journal_directory_is_optional(tmp_path: Path):
    state = read_elite_state(tmp_path / "not-installed")

    assert state.available is False
    assert "not found" in state.warnings[0].lower()
