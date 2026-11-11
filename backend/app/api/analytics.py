"""Plant analytics: aggregated counts and downtime for the dashboard and analytics pages."""
from fastapi import APIRouter
from sqlalchemy import func, select

from ..db import DbSession
from ..models.db_models import Document, Equipment, WorkOrder
from ..retrieval import vector_store
from ..schemas import AnalyticsSummary, DocumentStat, EquipmentDowntime, MonthlyWorkOrders

router = APIRouter(prefix="/analytics", tags=["analytics"])

TOP_DOWNTIME_ROWS = 8
MAX_DOCUMENT_ROWS = 12


def _counts(db, column) -> dict[str, int]:
    return {value: count for value, count in db.execute(select(column, func.count()).group_by(column))}


@router.get("/summary", response_model=AnalyticsSummary, summary="Equipment, work-order and knowledge-base totals")
def summary(db: DbSession) -> AnalyticsSummary:
    by_status = _counts(db, WorkOrder.status)

    downtime_rows = db.execute(
        select(
            Equipment.tag,
            Equipment.name,
            func.coalesce(func.sum(WorkOrder.downtime_hours), 0.0),
            func.count(WorkOrder.id),
        )
        .join(WorkOrder, WorkOrder.equipment_id == Equipment.id)
        .group_by(Equipment.id)
        .order_by(func.sum(WorkOrder.downtime_hours).desc(), Equipment.tag)
        .limit(TOP_DOWNTIME_ROWS)
    ).all()

    year, month = func.extract("year", WorkOrder.created_at), func.extract("month", WorkOrder.created_at)
    monthly_rows = db.execute(
        select(year, month, func.count(), func.coalesce(func.sum(WorkOrder.downtime_hours), 0.0))
        .group_by(year, month)
        .order_by(year, month)
    ).all()

    chunks = vector_store.load_chunks()
    doc_totals = db.execute(select(func.count(), func.coalesce(func.sum(Document.pages), 0))).one()

    return AnalyticsSummary(
        equipment_total=db.scalar(select(func.count()).select_from(Equipment)) or 0,
        equipment_by_status=_counts(db, Equipment.status),
        work_orders_total=sum(by_status.values()),
        work_orders_open=sum(n for status, n in by_status.items() if status != "closed"),
        work_orders_by_status=by_status,
        work_orders_by_priority=_counts(db, WorkOrder.priority),
        downtime_hours_total=float(db.scalar(select(func.coalesce(func.sum(WorkOrder.downtime_hours), 0.0))) or 0.0),
        downtime_by_equipment=[
            EquipmentDowntime(tag=tag, name=name, hours=float(hours), work_orders=count)
            for tag, name, hours, count in downtime_rows
        ],
        work_orders_by_month=[
            MonthlyWorkOrders(month=f"{int(y):04d}-{int(m):02d}", work_orders=count, downtime_hours=float(hours))
            for y, m, count, hours in monthly_rows
        ],
        documents=doc_totals[0],
        pages=int(doc_totals[1]),
        passages=len(chunks),
        document_stats=[
            DocumentStat(filename=d.filename, pages=d.pages, passages=d.chunks, uploaded_at=d.uploaded_at)
            for d in db.scalars(select(Document).order_by(Document.uploaded_at.desc()).limit(MAX_DOCUMENT_ROWS))
        ],
    )