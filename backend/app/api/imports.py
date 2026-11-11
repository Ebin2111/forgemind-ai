"""Bulk import of equipment and work orders from a CSV or JSON file."""
import csv
import io
import json
import re
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select

from ..core.security import require_admin
from ..db import DbSession
from ..models.db_models import Equipment, WorkOrder
from ..schemas import EquipmentStatus, ImportResult, Priority, WorkOrderStatus
from .registry import _next_wo_number

router = APIRouter(prefix="/import", tags=["import"])

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
MAX_ERRORS = 20


class _Row(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


class EquipmentRow(_Row):
    tag: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=200)
    type: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=200)
    manufacturer: str = Field(default="", max_length=100)
    status: EquipmentStatus = "operational"


class WorkOrderRow(_Row):
    equipment_tag: str = Field(min_length=1)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)
    priority: Priority = "medium"
    status: WorkOrderStatus = "open"
    technician: str = Field(default="", max_length=100)
    created_at: date = Field(default_factory=date.today)
    downtime_hours: float = Field(default=0.0, ge=0, le=100000)
    wo_number: str | None = Field(default=None, max_length=50)

    @field_validator("priority", "status", mode="before")
    @classmethod
    def _lower(cls, v):
        return v.strip().lower().replace(" ", "_") if isinstance(v, str) else v


def _clean(raw: dict) -> dict:
    """Blank cells count as "not given", so the field's default applies."""
    return {k: v for k, v in raw.items() if v is not None and not (isinstance(v, str) and not v.strip())}


def _header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


async def _rows(upload: UploadFile) -> list[dict]:
    raw = await upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "File is larger than 2 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is not UTF-8 text. Save it as CSV (UTF-8).")
    name = (upload.filename or "").lower()
    if name.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is not valid JSON.")
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        rows = [{_header(str(k)): v for k, v in r.items()} for r in data if isinstance(r, dict)]
    elif name.endswith(".csv"):
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        rows = [{_header(k or ""): v for k, v in r.items() if k} for r in reader]
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a .csv or .json file.")
    if not rows:
        raise HTTPException(422, "The file has no data rows.")
    if len(rows) > MAX_ROWS:
        raise HTTPException(413, f"At most {MAX_ROWS} rows per file.")
    return rows


def _why(exc: ValidationError) -> str:
    e = exc.errors()[0]
    where = ".".join(str(p) for p in e["loc"]) or "row"
    return f"{where}: {e['msg']}"


@router.post("/equipment", response_model=ImportResult, summary="Import equipment from CSV or JSON", dependencies=[Depends(require_admin)])
async def import_equipment(db: DbSession, file: UploadFile = File(...)) -> ImportResult:
    """Columns: tag, name (required); type, location, manufacturer, status (optional). Existing tags are skipped."""
    result = ImportResult(added=0, skipped=0)
    known = {t.lower() for (t,) in db.execute(select(Equipment.tag))}
    for number, raw in enumerate(await _rows(file), start=2):
        try:
            row = EquipmentRow.model_validate(_clean(raw))
        except ValidationError as exc:
            result.skipped += 1
            if len(result.errors) < MAX_ERRORS:
                result.errors.append(f"Row {number}: {_why(exc)}")
            continue
        tag = row.tag.upper()
        if tag.lower() in known:
            result.skipped += 1
            if len(result.errors) < MAX_ERRORS:
                result.errors.append(f"Row {number}: tag {tag} already exists")
            continue
        known.add(tag.lower())
        db.add(Equipment(**{**row.model_dump(), "tag": tag}))
        result.added += 1
    db.commit()
    return result


@router.post("/work-orders", response_model=ImportResult, summary="Import work orders from CSV or JSON", dependencies=[Depends(require_admin)])
async def import_work_orders(db: DbSession, file: UploadFile = File(...)) -> ImportResult:
    """Columns: equipment_tag, title (required); description, priority, status, technician, created_at (YYYY-MM-DD),
    downtime_hours, wo_number (optional). The equipment must already be in the registry."""
    result = ImportResult(added=0, skipped=0)
    by_tag = {t.lower(): i for i, t in db.execute(select(Equipment.id, Equipment.tag))}
    used = {n.lower() for (n,) in db.execute(select(WorkOrder.wo_number))}
    for number, raw in enumerate(await _rows(file), start=2):
        def skip(reason: str) -> None:
            result.skipped += 1
            if len(result.errors) < MAX_ERRORS:
                result.errors.append(f"Row {number}: {reason}")

        try:
            row = WorkOrderRow.model_validate(_clean(raw))
        except ValidationError as exc:
            skip(_why(exc))
            continue
        equipment_id = by_tag.get(row.equipment_tag.lower())
        if equipment_id is None:
            skip(f"equipment {row.equipment_tag} is not in the registry")
            continue
        wo_number = row.wo_number or _next_wo_number(db)
        if wo_number.lower() in used:
            skip(f"{wo_number} already exists")
            continue
        used.add(wo_number.lower())
        data = row.model_dump(exclude={"equipment_tag", "wo_number"})
        db.add(WorkOrder(wo_number=wo_number, equipment_id=equipment_id, **data))
        db.flush()  # so the next generated number sees this one
        result.added += 1
    db.commit()
    return result