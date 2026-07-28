from __future__ import annotations

import gzip
import json
import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .database import Commodity, MarketObservation, Station, System


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


class MarketProvider(ABC):
    @abstractmethod
    async def search_locations(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError


class SpanshRemoteProvider(MarketProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def search_locations(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    response = await client.get(f"{self.settings.spansh_base_url}/search", params={"q": query})
                    response.raise_for_status()
                    payload = response.json()
                    records = payload.get("results", payload if isinstance(payload, list) else [])
                    return list(records)[:limit]
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    if attempt < 2:
                        import asyncio

                        await asyncio.sleep(0.25 * (2**attempt))
            raise RuntimeError(f"Spansh location search unavailable: {last_error}")

    async def fetch_system_dump(self, id64: int) -> dict[str, Any]:
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(f"{self.settings.spansh_base_url}/dump/{id64}")
            response.raise_for_status()
            return response.json()

    async def hydrate_trade_candidates(
        self,
        session: Session,
        *,
        origin_id64: int,
        cargo_capacity: int,
        min_supply_multiplier: float,
        max_distance_ly: float,
    ) -> int:
        importer = SpanshDumpProvider(session)
        payload = await self.fetch_system_dump(origin_id64)
        system_record = payload.get("system", payload.get("record", payload))
        importer.import_record(system_record, "spansh_remote")
        # Do not keep a SQLite write transaction open while waiting for the
        # remote commodity searches. A data-pack job may be reporting progress
        # from another thread at the same time.
        session.commit()
        sources = list(
            session.scalars(
                select(MarketObservation)
                .join(Station)
                .where(
                    Station.system_id64 == origin_id64,
                    MarketObservation.buy_price > 0,
                    MarketObservation.supply >= max(1, round(cargo_capacity * min_supply_multiplier)),
                )
            ).all()
        )
        sources.sort(key=lambda item: item.buy_price * min(item.supply, cargo_capacity), reverse=True)
        selected: list[tuple[str, int]] = []
        seen: set[int] = set()
        for source in sources:
            if source.commodity_id in seen:
                continue
            seen.add(source.commodity_id)
            selected.append((source.commodity.display_name, source.commodity_id))
            if len(selected) >= 12:
                break
        if not selected:
            session.commit()
            return 0

        semaphore = asyncio.Semaphore(self.settings.remote_concurrency)
        timeout = httpx.Timeout(max(30.0, self.settings.request_timeout_seconds))

        async def fetch_one(name: str, commodity_id: int) -> tuple[int, list[dict[str, Any]]]:
            endpoint = (
                f"{self.settings.spansh_base_url}/commodity/sell/"
                f"{quote(system_record['name'], safe='')}/{quote(name, safe='')}/{cargo_capacity}"
            )
            async with semaphore:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.get(endpoint)
                    response.raise_for_status()
                    data = response.json()
                    return commodity_id, list(data.get("results", []))

        batches = await asyncio.gather(
            *(fetch_one(name, commodity_id) for name, commodity_id in selected),
            return_exceptions=True,
        )
        imported = 0
        for batch in batches:
            if isinstance(batch, Exception):
                continue
            _, records = batch
            for record in records:
                if float(record.get("distance", 0) or 0) > max_distance_ly:
                    continue
                importer.upsert_remote_station(record, "spansh_remote")
                imported += 1
        session.commit()
        return imported

    def cache_search_results(self, session: Session, results: list[dict[str, Any]]) -> None:
        importer = SpanshDumpProvider(session)
        for result in results:
            record = result.get("record", result)
            kind = result.get("type")
            if kind == "system":
                importer.import_record(record, "spansh_remote")
            elif kind == "station":
                importer.upsert_remote_station(record, "spansh_remote")
        session.commit()


class SpanshDumpProvider:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_file(self, path: Path, provider: str = "spansh_dump") -> dict[str, int]:
        counts = {"systems": 0, "stations": 0, "commodities": 0, "observations": 0}
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as stream:
            for record in _iter_json_records(iter(lambda: stream.read(1024 * 1024), "")):
                self._upsert_system(record, provider, counts)
        self.session.commit()
        return counts

    def import_record(self, record: dict[str, Any], provider: str = "spansh_remote") -> dict[str, int]:
        counts = {"systems": 0, "stations": 0, "commodities": 0, "observations": 0}
        self._upsert_system(record, provider, counts)
        self.session.flush()
        return counts

    def upsert_remote_station(self, record: dict[str, Any], provider: str = "spansh_remote") -> None:
        system_id64 = record.get("system_id64")
        if not system_id64:
            return
        updated = _parse_time(record.get("updated_at"))
        system = self.session.get(System, int(system_id64))
        if system is None:
            system_name = record.get("system_name") or f"System {system_id64}"
            system = System(
                id64=int(system_id64),
                name=system_name,
                normalized_name=normalized(system_name),
                x=float(record.get("system_x", 0) or 0),
                y=float(record.get("system_y", 0) or 0),
                z=float(record.get("system_z", 0) or 0),
                permit_required=False,
                updated_at=updated,
            )
            self.session.add(system)
            self.session.flush()
        station_record = {
            **record,
            "marketId": record.get("market_id"),
            "distanceToArrival": record.get("distance_to_arrival", 0),
            "isPlanetary": record.get("is_planetary", False),
            "updateTime": record.get("updated_at"),
            "market": {
                "updateTime": record.get("market_updated_at") or record.get("updated_at"),
                "commodities": [
                    {
                        "name": item.get("commodity"),
                        "category": item.get("category"),
                        "buyPrice": item.get("buy_price", 0),
                        "sellPrice": item.get("sell_price", 0),
                        "stock": item.get("supply", 0),
                        "demand": item.get("demand", 0),
                    }
                    for item in record.get("market", [])
                ],
            },
        }
        counts = {"systems": 0, "stations": 0, "commodities": 0, "observations": 0}
        self._upsert_station(system, station_record, provider, updated, counts)

    def _upsert_system(self, record: dict[str, Any], provider: str, counts: dict[str, int]) -> None:
        id64 = record.get("id64") or record.get("id")
        name = record.get("name")
        coords = record.get("coords") or {}
        if not id64 or not name:
            return
        updated = _parse_time(record.get("date") or record.get("updateTime"))
        system = self.session.get(System, int(id64))
        if system is None:
            system = System(
                id64=int(id64),
                name=name,
                normalized_name=normalized(name),
                x=float(record.get("x", coords.get("x", 0))),
                y=float(record.get("y", coords.get("y", 0))),
                z=float(record.get("z", coords.get("z", 0))),
                permit_required=bool(record.get("needsPermit", False)),
                updated_at=updated,
            )
            self.session.add(system)
            counts["systems"] += 1
        for station_record in record.get("stations") or []:
            self._upsert_station(system, station_record, provider, updated, counts)
        for body in record.get("bodies") or []:
            for station_record in body.get("stations") or []:
                self._upsert_station(system, station_record, provider, updated, counts)

    def _upsert_station(
        self,
        system: System,
        record: dict[str, Any],
        provider: str,
        fallback_time: datetime,
        counts: dict[str, int],
    ) -> None:
        market_id = record.get("marketId") or record.get("market_id") or record.get("id")
        if not market_id:
            return
        updated = _parse_time(record.get("updateTime") or record.get("updated_at"), fallback_time)
        station = self.session.get(Station, int(market_id))
        if station is None:
            station_type = record.get("type") or "Unknown"
            station = Station(
                market_id=int(market_id),
                system_id64=system.id64,
                name=record.get("name") or f"Market {market_id}",
                normalized_name=normalized(record.get("name") or f"Market {market_id}"),
                station_type=station_type,
                distance_to_arrival_ls=float(record.get("distanceToArrival", record.get("distance_to_arrival", 0)) or 0),
                largest_pad=_largest_pad(record),
                planetary=bool(record.get("isPlanetary", record.get("is_planetary", False))),
                fleet_carrier="carrier" in station_type.casefold(),
                odyssey=bool(record.get("isOdyssey", record.get("is_odyssey", False))),
                restricted=bool(record.get("isRestricted", False)),
                updated_at=updated,
            )
            self.session.add(station)
            counts["stations"] += 1
        market = record.get("market") or {}
        market_updated = _parse_time(
            market.get("updateTime") if isinstance(market, dict) else None,
            updated,
        )
        commodities = market.get("commodities") if isinstance(market, dict) else market
        for item in commodities or record.get("commodities") or []:
            canonical = str(item.get("symbol") or item.get("name") or "").strip()
            if not canonical:
                continue
            commodity = self.session.scalar(select(Commodity).where(Commodity.canonical_name == normalized(canonical)))
            if commodity is None:
                commodity = Commodity(
                    id=int(item["commodityId"]) if item.get("commodityId") else None,
                    canonical_name=normalized(canonical),
                    display_name=item.get("name_localised") or item.get("name") or canonical,
                    category=item.get("category") or "Unknown",
                )
                self.session.add(commodity)
                self.session.flush()
                counts["commodities"] += 1
            observation = self.session.scalar(
                select(MarketObservation).where(
                    MarketObservation.market_id == station.market_id,
                    MarketObservation.commodity_id == commodity.id,
                )
            )
            if observation is None:
                observation = MarketObservation(
                    market_id=station.market_id,
                    commodity_id=commodity.id,
                    buy_price=int(item.get("buyPrice", item.get("buy_price", 0)) or 0),
                    sell_price=int(item.get("sellPrice", item.get("sell_price", 0)) or 0),
                    supply=int(item.get("stock", item.get("supply", 0)) or 0),
                    demand=int(item.get("demand", 0) or 0),
                    observed_at=market_updated,
                    provider=provider,
                )
                self.session.add(observation)
                counts["observations"] += 1
            elif _parse_time(observation.observed_at) <= market_updated:
                observation.buy_price = int(item.get("buyPrice", item.get("buy_price", 0)) or 0)
                observation.sell_price = int(item.get("sellPrice", item.get("sell_price", 0)) or 0)
                observation.supply = int(item.get("stock", item.get("supply", 0)) or 0)
                observation.demand = int(item.get("demand", 0) or 0)
                observation.observed_at = market_updated
                observation.provider = provider


def _largest_pad(record: dict[str, Any]) -> str:
    landing_pads = record.get("landingPads") or {}
    if landing_pads.get("large", 0):
        return "L"
    if landing_pads.get("medium", 0):
        return "M"
    if record.get("has_large_pad") or record.get("largePads", 0) or record.get("large_pads", 0):
        return "L"
    if record.get("mediumPads", 0) or record.get("medium_pads", 0):
        return "M"
    return "S"


def _parse_time(value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return fallback or datetime.now(UTC)


def _iter_json_records(stream: Iterable[str]) -> Iterable[dict[str, Any]]:
    decoder = json.JSONDecoder()
    buffer = ""
    in_array = False
    for chunk in stream:
        buffer += chunk
        while True:
            buffer = buffer.lstrip()
            if not buffer:
                break
            if not in_array and buffer.startswith("["):
                in_array = True
                buffer = buffer[1:]
                continue
            if buffer.startswith(","):
                buffer = buffer[1:]
                continue
            if buffer.startswith("]"):
                return
            try:
                item, index = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                break
            if isinstance(item, dict):
                yield item
            buffer = buffer[index:]
