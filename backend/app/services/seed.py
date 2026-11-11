"""Load sample industrial data (equipment + work orders) into the database.

* Idempotent: records are matched on ``tag`` / ``wo_number`` and only missing ones are inserted,
  so restarting the app never duplicates rows or overwrites edits made since.
* Validated: each record is checked against the same rules as the API; bad records are skipped
  and logged instead of aborting startup.
* The caller owns the transaction (``session_scope()`` commits). This function only flushes.

CLI:
    python -m backend.app.services.seed                 # insert anything missing
    python -m backend.app.services.seed --path my.json  # use another file
    python -m backend.app.services.seed --reset         # delete ALL equipment/work orders first
"""
import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.db_models import Equipment, WorkOrder
from ..schemas import EquipmentStatus, Priority, WorkOrderStatus

logger = logging.getLogger(__name__)

DEFAULT_PATH = settings.sample_dir / "maintenance_records.json"


class EquipmentRecord(BaseModel):
    tag: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=200)
    manufacturer: str = Field(default="", max_length=100)
    status: EquipmentStatus = "operational"


class WorkOrderRecord(BaseModel):
    wo_number: str = Field(min_length=1, max_length=50)
    equipment_tag: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    priority: Priority = "medium"
    status: WorkOrderStatus = "open"
    technician: str = Field(default="", max_length=100)
    created_at: date
    downtime_hours: float = Field(default=0.0, ge=0)


@dataclass
class SeedResult:
    equipment_added: int = 0
    work_orders_added: int = 0
    skipped: int = 0

    @property
    def total_added(self) -> int:
        return self.equipment_added + self.work_orders_added

    def __bool__(self) -> bool:  # `if seed_sample_data(db):` means "did anything change"
        return self.total_added > 0


def _load_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value must be an object with 'equipment' and 'work_orders'")
    return data


def _valid(model: type[BaseModel], raw: object, kind: str) -> BaseModel | None:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        logger.warning("Skipping invalid %s record (%s: %s): %r", kind, ".".join(map(str, first["loc"])), first["msg"], raw)
        return None


def seed_sample_data(db: Session, path: Path | str | None = None) -> SeedResult:
    """Insert missing sample equipment and work orders. Never raises on bad sample data."""
    path = Path(path) if path else DEFAULT_PATH
    result = SeedResult()

    if not path.exists():
        logger.info("No sample data file at %s; nothing to seed", path)
        return result
    try:
        data = _load_file(path)
    except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
        logger.error("Could not read sample data %s: %s", path, exc)
        return result

    known_tags = set(db.scalars(select(Equipment.tag)))
    for raw in data.get("equipment", []):
        record = _valid(EquipmentRecord, raw, "equipment")
        if record is None:
            result.skipped += 1
        elif record.tag in known_tags:
            continue
        else:
            db.add(Equipment(**record.model_dump()))
            known_tags.add(record.tag)
            result.equipment_added += 1
    db.flush()  # assigns primary keys so work orders can reference them

    equipment_ids = dict(db.execute(select(Equipment.tag, Equipment.id)).all())
    known_orders = set(db.scalars(select(WorkOrder.wo_number)))
    for raw in data.get("work_orders", []):
        record = _valid(WorkOrderRecord, raw, "work order")
        if record is None:
            result.skipped += 1
            continue
        if record.wo_number in known_orders:
            continue
        equipment_id = equipment_ids.get(record.equipment_tag)
        if equipment_id is None:
            logger.warning("Skipping %s: unknown equipment tag %r", record.wo_number, record.equipment_tag)
            result.skipped += 1
            continue
        db.add(WorkOrder(equipment_id=equipment_id, **record.model_dump(exclude={"equipment_tag"})))
        known_orders.add(record.wo_number)
        result.work_orders_added += 1
    db.flush()

    logger.info(
        "Seed complete: +%d equipment, +%d work orders, %d skipped",
        result.equipment_added, result.work_orders_added, result.skipped,
    )
    return result


def reset_sample_data(db: Session) -> None:
    """Delete ALL work orders and equipment (not just sample rows). Destructive; CLI use only."""
    db.execute(delete(WorkOrder))
    db.execute(delete(Equipment))
    db.flush()


def main(argv: list[str] | None = None) -> int:
    from ..core.logging import configure_logging
    from ..db import init_db, session_scope

    parser = argparse.ArgumentParser(description="Seed ForgeMind sample data.")
    parser.add_argument("--path", type=Path, help="JSON file to load (default: data/sample/maintenance_records.json)")
    parser.add_argument("--reset", action="store_true", help="delete ALL equipment and work orders first")
    args = parser.parse_args(argv)

    configure_logging(settings.log_level)
    init_db()
    with session_scope() as db:
        if args.reset:
            reset_sample_data(db)
            logger.warning("Existing equipment and work orders deleted")
        result = seed_sample_data(db, args.path)
    print(f"Added {result.equipment_added} equipment and {result.work_orders_added} work orders ({result.skipped} skipped).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())