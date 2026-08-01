"""Deterministic, persisted operational alerts for ION Computer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import (
    ActiveOperation,
    ComputerAlert,
    ComputerAlertSnooze,
    MarketObservation,
)
from .events import event_bus
from .schemas import ComputerPreferences


SCOOPABLE_STARS = frozenset("KGBFOAM")
CRITICAL_CATEGORIES = frozenset({"fuel_risk", "overheating", "hull_risk", "canopy_risk"})
ALERT_CATEGORIES = (
    "fuel_risk",
    "no_scoopable_star",
    "overheating",
    "hull_risk",
    "canopy_risk",
    "cargo_mismatch",
    "passed_destination",
    "market_expiry",
    "insufficient_demand",
    "reduced_range",
    "unreachable_route",
    "operation_step",
    "game_link",
    "service_opportunity",
)
COOLDOWNS = {
    "fuel_risk": 120,
    "no_scoopable_star": 300,
    "overheating": 90,
    "hull_risk": 180,
    "canopy_risk": 180,
    "cargo_mismatch": 300,
    "passed_destination": 300,
    "market_expiry": 900,
    "insufficient_demand": 900,
    "reduced_range": 300,
    "unreachable_route": 300,
    "operation_step": 30,
    "game_link": 180,
    "service_opportunity": 900,
}


@dataclass(frozen=True)
class AlertCandidate:
    category: str
    severity: str
    title: str
    message: str
    facts: dict[str, Any]
    interrupt_allowed: bool = False

    @property
    def fingerprint(self) -> str:
        value = {
            "category": self.category,
            "facts": self.facts,
        }
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def serialize_alert(record: ComputerAlert) -> dict[str, Any]:
    return {
        "id": record.id,
        "fingerprint": record.fingerprint,
        "category": record.category,
        "severity": record.severity,
        "title": record.title,
        "message": record.message,
        "facts": record.facts,
        "status": record.status,
        "interrupt_allowed": record.interrupt_allowed,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "acknowledged_at": (
            record.acknowledged_at.isoformat() if record.acknowledged_at else None
        ),
    }


def _cargo_by_name(state: dict[str, Any]) -> dict[str, int]:
    return {
        str(item.get("canonical_commodity") or item.get("commodity") or "")
        .casefold()
        .strip(): int(item.get("count") or 0)
        for item in state.get("cargo") or []
        if isinstance(item, dict)
    }


def _active_leg(operation: ActiveOperation | None) -> dict[str, Any] | None:
    if operation is None:
        return None
    legs = (operation.route_payload or {}).get("legs") or []
    if not legs or operation.manual_progress >= len(legs):
        return None
    leg = legs[operation.manual_progress]
    return leg if isinstance(leg, dict) else None


def evaluate_alerts(
    state: dict[str, Any],
    previous: dict[str, Any] | None,
    operation: ActiveOperation | None,
    previous_operation: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    session: Session | None = None,
) -> list[AlertCandidate]:
    now = now or datetime.now(UTC)
    candidates: list[AlertCandidate] = []
    flags = set(state.get("status_flags") or [])
    fuel_percent = state.get("fuel_percent")
    hull_health = state.get("hull_health")
    canopy_health = state.get("canopy_health")

    if "Low fuel" in flags or (
        isinstance(fuel_percent, (int, float)) and fuel_percent <= 15
    ):
        candidates.append(
            AlertCandidate(
                "fuel_risk",
                "critical",
                "Fuel risk",
                f"Fuel is at {fuel_percent:.0f}%." if fuel_percent is not None else "Elite reports low fuel.",
                {"fuel_percent": fuel_percent, "low_fuel_flag": "Low fuel" in flags},
                True,
            )
        )
    if "Overheating" in flags:
        candidates.append(
            AlertCandidate(
                "overheating",
                "critical",
                "Ship overheating",
                "Elite reports an overheating condition.",
                {"flag": "Overheating"},
                True,
            )
        )
    if isinstance(hull_health, (int, float)) and hull_health <= 30:
        candidates.append(
            AlertCandidate(
                "hull_risk",
                "critical",
                "Hull integrity critical",
                f"Hull integrity is {hull_health:.0f}%.",
                {"hull_health": round(float(hull_health), 1)},
                True,
            )
        )
    if isinstance(canopy_health, (int, float)) and canopy_health <= 30:
        candidates.append(
            AlertCandidate(
                "canopy_risk",
                "critical",
                "Canopy integrity critical",
                f"Canopy integrity is {canopy_health:.0f}%.",
                {"canopy_health": round(float(canopy_health), 1)},
                True,
            )
        )

    route = state.get("nav_route") or []
    if (
        fuel_percent is not None
        and fuel_percent <= 35
        and route
        and not any(
            str(item.get("star_class") or "")[:1].upper() in SCOOPABLE_STARS
            for item in route[1:6]
            if isinstance(item, dict)
        )
    ):
        candidates.append(
            AlertCandidate(
                "no_scoopable_star",
                "warning",
                "No scoopable star ahead",
                "Fuel is reduced and the next five plotted systems contain no known scoopable star.",
                {"fuel_percent": round(float(fuel_percent), 1), "checked_systems": min(5, len(route) - 1)},
            )
        )

    if previous and previous.get("game_running") and not state.get("game_running"):
        candidates.append(
            AlertCandidate(
                "game_link",
                "warning",
                "Elite link changed",
                "Elite is no longer detected. Saved telemetry remains available.",
                {"previously_running": True, "currently_running": False},
            )
        )

    leg = _active_leg(operation)
    if leg:
        commodity = str(
            leg.get("canonical_commodity") or leg.get("commodity") or ""
        ).casefold()
        required = int(leg.get("quantity") or 0)
        aboard = _cargo_by_name(state).get(commodity, 0)
        if commodity and required and aboard < required:
            candidates.append(
                AlertCandidate(
                    "cargo_mismatch",
                    "warning",
                    "Cargo does not match operation",
                    f"Operation expects {required} t of {leg.get('commodity') or commodity}; {aboard} t is aboard.",
                    {
                        "commodity": commodity,
                        "required": required,
                        "aboard": aboard,
                        "step": operation.manual_progress if operation else 0,
                    },
                )
            )
        destination_id = leg.get("destination_system_id64")
        if (
            destination_id
            and previous
            and previous.get("system_id64") == destination_id
            and state.get("system_id64") != destination_id
        ):
            candidates.append(
                AlertCandidate(
                    "passed_destination",
                    "warning",
                    "Destination passed",
                    "The vessel left the active leg destination before the operation advanced.",
                    {"destination_system_id64": int(destination_id)},
                )
            )
        required_range = float(leg.get("required_jump_range") or 0)
        current_range = float(state.get("max_jump_range") or 0)
        if required_range and current_range and current_range < required_range:
            candidates.append(
                AlertCandidate(
                    "reduced_range",
                    "warning",
                    "Loaded range below plan",
                    f"Current range is {current_range:.1f} ly; this leg requires {required_range:.1f} ly.",
                    {
                        "current_range": round(current_range, 2),
                        "required_range": round(required_range, 2),
                    },
                )
            )
        observed_at = leg.get("destination_observed_at")
        if observed_at:
            try:
                observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=UTC)
                age_hours = (now - observed).total_seconds() / 3600
                if age_hours >= 4:
                    candidates.append(
                        AlertCandidate(
                            "market_expiry",
                            "warning",
                            "Market observation is stale",
                            f"Destination market data is {age_hours:.1f} hours old.",
                            {
                                "market_id": leg.get("destination_market_id"),
                                "age_hours": round(age_hours, 1),
                            },
                        )
                    )
            except (TypeError, ValueError):
                pass
        if session and leg.get("destination_market_id") and leg.get("commodity_id"):
            observation = session.scalar(
                select(MarketObservation).where(
                    MarketObservation.market_id == int(leg["destination_market_id"]),
                    MarketObservation.commodity_id == int(leg["commodity_id"]),
                )
            )
            if observation and required and observation.demand < required:
                candidates.append(
                    AlertCandidate(
                        "insufficient_demand",
                        "warning",
                        "Destination demand is insufficient",
                        f"Observed demand is {observation.demand} t for {required} t of planned cargo.",
                        {
                            "market_id": observation.market_id,
                            "demand": observation.demand,
                            "required": required,
                        },
                    )
                )

    if (
        operation
        and previous_operation
        and operation.manual_progress > int(previous_operation.get("manual_progress") or 0)
    ):
        candidates.append(
            AlertCandidate(
                "operation_step",
                "information",
                "Operation step completed",
                f"Operation advanced to step {operation.manual_progress + 1}.",
                {
                    "operation": operation.title,
                    "manual_progress": operation.manual_progress,
                },
            )
        )
    return candidates


class ComputerAlertEngine:
    def __init__(self) -> None:
        self._previous_operation: dict[str, Any] | None = None

    def process(
        self,
        session: Session,
        state: dict[str, Any],
        previous: dict[str, Any] | None,
        preferences: ComputerPreferences,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now or datetime.now(UTC)
        operation = session.get(ActiveOperation, 1)
        candidates = evaluate_alerts(
            state,
            previous,
            operation,
            self._previous_operation,
            now=now,
            session=session,
        )
        self._previous_operation = (
            {
                "manual_progress": operation.manual_progress,
                "status": operation.status,
            }
            if operation
            else None
        )
        emitted: list[dict[str, Any]] = []
        active_categories = {candidate.category for candidate in candidates}
        active = session.scalars(
            select(ComputerAlert).where(ComputerAlert.status == "active")
        ).all()
        for record in active:
            if record.category not in active_categories:
                record.status = "resolved"
                record.updated_at = now

        disabled = set(preferences.disabled_alert_categories)
        snoozes = {
            row.category: row.snoozed_until
            for row in session.scalars(select(ComputerAlertSnooze)).all()
        }
        for candidate in candidates:
            if (
                preferences.proactivity == "critical"
                and candidate.severity != "critical"
            ):
                continue
            if (
                candidate.category in disabled
                and candidate.category not in CRITICAL_CATEGORIES
            ):
                continue
            snoozed_until = snoozes.get(candidate.category)
            if snoozed_until:
                if snoozed_until.tzinfo is None:
                    snoozed_until = snoozed_until.replace(tzinfo=UTC)
                if snoozed_until > now and candidate.category not in CRITICAL_CATEGORIES:
                    continue
            cutoff = now - timedelta(seconds=COOLDOWNS.get(candidate.category, 300))
            duplicate = session.scalar(
                select(ComputerAlert)
                .where(
                    ComputerAlert.fingerprint == candidate.fingerprint,
                    ComputerAlert.created_at >= cutoff,
                )
                .order_by(ComputerAlert.created_at.desc())
            )
            if duplicate:
                continue
            record = ComputerAlert(
                id=str(uuid4()),
                fingerprint=candidate.fingerprint,
                category=candidate.category,
                severity=candidate.severity,
                title=candidate.title,
                message=candidate.message,
                facts=candidate.facts,
                status="active",
                interrupt_allowed=candidate.interrupt_allowed,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            payload = serialize_alert(record)
            emitted.append(payload)
            event_bus.publish("computer.alert.raised", payload)
        session.commit()
        return emitted


def acknowledge_alert(session: Session, alert_id: str) -> dict[str, Any]:
    record = session.get(ComputerAlert, alert_id)
    if record is None:
        raise LookupError("Computer alert was not found.")
    record.status = "acknowledged"
    record.acknowledged_at = datetime.now(UTC)
    record.updated_at = record.acknowledged_at
    session.commit()
    result = serialize_alert(record)
    event_bus.publish("computer.alert.acknowledged", result)
    return result


def snooze_category(
    session: Session, category: str, minutes: int
) -> dict[str, Any]:
    category = category.strip().casefold()
    if category not in ALERT_CATEGORIES:
        raise ValueError("Unknown Computer alert category.")
    if category in CRITICAL_CATEGORIES:
        raise ValueError("Critical alert categories cannot be snoozed.")
    if minutes < 1 or minutes > 1440:
        raise ValueError("Snooze duration must be between 1 and 1,440 minutes.")
    now = datetime.now(UTC)
    record = session.get(ComputerAlertSnooze, category)
    if record is None:
        record = ComputerAlertSnooze(
            category=category,
            snoozed_until=now + timedelta(minutes=minutes),
            updated_at=now,
        )
        session.add(record)
    else:
        record.snoozed_until = now + timedelta(minutes=minutes)
        record.updated_at = now
    session.commit()
    result = {
        "category": category,
        "snoozed_until": record.snoozed_until.isoformat(),
    }
    event_bus.publish("computer.alert.snoozed", result)
    return result


def list_alerts(
    session: Session, *, limit: int = 100, statuses: Iterable[str] = ("active",)
) -> list[dict[str, Any]]:
    records = session.scalars(
        select(ComputerAlert)
        .where(ComputerAlert.status.in_(tuple(statuses)))
        .order_by(ComputerAlert.created_at.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    return [serialize_alert(record) for record in records]


computer_alert_engine = ComputerAlertEngine()
