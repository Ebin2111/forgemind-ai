"""Equipment registry and maintenance work orders."""
from typing import Optional

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status as http
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from ..core.security import CurrentUser, require_admin, require_user
from ..db import DbSession
from ..models.db_models import Equipment, WorkOrder
from ..schemas import (
    DeleteOut,
    EquipmentCreate,
    EquipmentOut,
    EquipmentStatus,
    EquipmentUpdate,
    Priority,
    WorkOrderCreate,
    WorkOrderOut,
    WorkOrderStatus,
    WorkOrderUpdate,
)

router = APIRouter(tags=["registry"])


@router.get("/equipment", response_model=list[EquipmentOut], summary="List equipment")
def list_equipment(
    response: Response,
    db: DbSession,
    status: Optional[EquipmentStatus] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(Equipment)
    if status:
        stmt = stmt.where(Equipment.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    response.headers["X-Total-Count"] = str(total or 0)
    return db.scalars(stmt.order_by(Equipment.tag).limit(limit).offset(offset)).all()


@router.post(
    "/equipment", response_model=EquipmentOut, status_code=http.HTTP_201_CREATED, summary="Add equipment",
    dependencies=[Depends(require_admin)],
)
def create_equipment(body: EquipmentCreate, db: DbSession):
    tag = body.tag.upper()
    if db.scalar(select(Equipment.id).where(func.lower(Equipment.tag) == tag.lower())):
        raise HTTPException(http.HTTP_409_CONFLICT, f"Tag {tag} is already used by another machine.")
    machine = Equipment(**{**body.model_dump(), "tag": tag})
    db.add(machine)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(http.HTTP_409_CONFLICT, f"Tag {tag} is already used by another machine.")
    db.refresh(machine)
    return machine


def _equipment_or_404(db, equipment_id: int) -> Equipment:
    machine = db.get(Equipment, equipment_id)
    if machine is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Equipment not found.")
    return machine


@router.patch("/equipment/{equipment_id}", response_model=EquipmentOut, summary="Edit equipment or change its status")
def update_equipment(
    equipment_id: int, body: EquipmentUpdate, db: DbSession, user: CurrentUser = Depends(require_user)
):
    machine = _equipment_or_404(db, equipment_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not user.is_admin and set(changes) - {"status"}:  # technicians may only change the machine's status
        raise HTTPException(http.HTTP_403_FORBIDDEN, "Only an administrator can edit machine details.")
    for field, value in changes.items():
        setattr(machine, field, value)
    db.commit()
    db.refresh(machine)
    return machine


@router.delete(
    "/equipment/{equipment_id}", response_model=DeleteOut, summary="Delete equipment and its work orders",
    dependencies=[Depends(require_admin)],
)
def delete_equipment(equipment_id: int, db: DbSession):
    machine = _equipment_or_404(db, equipment_id)
    tag = machine.tag
    db.delete(machine)
    db.commit()
    return DeleteOut(deleted=tag)


@router.get("/maintenance", response_model=list[WorkOrderOut], summary="List work orders")
def list_work_orders(
    response: Response,
    db: DbSession,
    status: Optional[WorkOrderStatus] = None,
    priority: Optional[Priority] = None,
    equipment_id: Optional[int] = None,
    q: Optional[str] = Query(None, max_length=100, description="Search work-order number, title or description"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(WorkOrder)
    if q and q.strip():
        like = "%" + re.sub(r"([\\%_])", r"\\\1", q.strip()) + "%"  # treat %, _ and \ as plain characters
        stmt = stmt.where(
            or_(
                WorkOrder.wo_number.ilike(like, escape="\\"),
                WorkOrder.title.ilike(like, escape="\\"),
                WorkOrder.description.ilike(like, escape="\\"),
            )
        )
    if status:
        stmt = stmt.where(WorkOrder.status == status)
    if priority:
        stmt = stmt.where(WorkOrder.priority == priority)
    if equipment_id is not None:
        stmt = stmt.where(WorkOrder.equipment_id == equipment_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    response.headers["X-Total-Count"] = str(total or 0)
    return db.scalars(stmt.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc()).limit(limit).offset(offset)).all()


_WO_NUMBER = re.compile(r"^WO-(\d+)$")
FIRST_WO_NUMBER = 1001


def _next_wo_number(db) -> str:
    """WO-<highest existing number + 1>; numbers that do not follow the WO-#### pattern are ignored."""
    numbers = [int(m.group(1)) for (n,) in db.execute(select(WorkOrder.wo_number)) if (m := _WO_NUMBER.match(n))]
    return f"WO-{max(numbers) + 1 if numbers else FIRST_WO_NUMBER}"


@router.post(
    "/maintenance",
    response_model=WorkOrderOut,
    status_code=http.HTTP_201_CREATED,
    summary="Create a work order",
)
def create_work_order(body: WorkOrderCreate, db: DbSession):
    if db.get(Equipment, body.equipment_id) is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Equipment not found.")
    for _ in range(3):  # two simultaneous requests can pick the same number; the database rejects the second
        order = WorkOrder(wo_number=_next_wo_number(db), status="open", **body.model_dump())
        db.add(order)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(order)
        return order
    raise HTTPException(http.HTTP_409_CONFLICT, "Could not allocate a work-order number. Please try again.")


def _work_order_or_404(db, work_order_id: int) -> WorkOrder:
    order = db.get(WorkOrder, work_order_id)
    if order is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Work order not found.")
    return order


@router.patch("/maintenance/{work_order_id}", response_model=WorkOrderOut, summary="Update a work order")
def update_work_order(work_order_id: int, body: WorkOrderUpdate, db: DbSession):
    order = _work_order_or_404(db, work_order_id)
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(order, field, value)
    db.commit()
    db.refresh(order)
    return order


@router.delete(
    "/maintenance/{work_order_id}", response_model=DeleteOut, summary="Delete a work order",
    dependencies=[Depends(require_admin)],
)
def delete_work_order(work_order_id: int, db: DbSession):
    order = _work_order_or_404(db, work_order_id)
    number = order.wo_number
    db.delete(order)
    db.commit()
    return DeleteOut(deleted=number)