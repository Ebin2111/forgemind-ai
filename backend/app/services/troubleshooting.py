"""Troubleshooting logic: machine context, similar past work orders, and the prompts built from them.

The API module stays thin; everything that can be tested without HTTP lives here.
"""
import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models.db_models import Equipment, WorkOrder
from ..retrieval.search import tokenize
from ..schemas import EquipmentHistory, RelatedWorkOrder, TroubleshootRequest

MAX_RELATED = 5  # similar work orders returned and given to the model
MAX_SCANNED = 500  # newest work orders considered when matching
MAX_TERMS = 8  # matched words listed per work order
DESCRIPTION_CHARS = 240  # per work order, in the model prompt
FAULT_CODE_BONUS = 5  # an exact fault-code hit outweighs several shared words

TASK = (
    "Task: using only the passages, list the most likely causes of this fault, the checks to make in "
    "order (safest and quickest first) and the corrective actions. Cite each statement. Use the "
    "machine details and past work orders only as context; they are not reference documents."
)


@dataclass
class TroubleshootingContext:
    equipment: Equipment | None = None
    history: EquipmentHistory | None = None
    related: list[RelatedWorkOrder] = field(default_factory=list)


def find_equipment(db: Session, tag: str) -> Equipment | None:
    """Look up equipment by tag, ignoring case ('p-101' finds 'P-101')."""
    return db.scalar(select(Equipment).where(func.lower(Equipment.tag) == tag.strip().lower()))


def equipment_history(db: Session, equipment: Equipment) -> EquipmentHistory:
    """Totals computed in SQL, so they stay correct however many work orders exist."""
    total, open_count, downtime, last = db.execute(
        select(
            func.count(WorkOrder.id),
            func.coalesce(func.sum(case((WorkOrder.status != "closed", 1), else_=0)), 0),  # portable CASE, not sum(bool)
            func.coalesce(func.sum(WorkOrder.downtime_hours), 0.0),
            func.max(WorkOrder.created_at),
        ).where(WorkOrder.equipment_id == equipment.id)
    ).one()
    return EquipmentHistory(
        work_orders_total=int(total or 0),
        work_orders_open=int(open_count or 0),
        downtime_hours_total=round(float(downtime or 0.0), 2),
        last_work_order_date=_as_date(last),
    )


def _as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


_RAW_WORD = re.compile(r"[a-z0-9]+(?:[-/_.][a-z0-9]+)*")


def _surface_forms(text: str) -> dict[str, str]:
    """Map each search term back to the word as the user typed it ('bear' -> 'bearing').

    Matching works on stemmed terms, but people reading the result should see real words.
    """
    forms: dict[str, str] = {}
    for word in _RAW_WORD.findall(text.lower()):
        for term in tokenize(word):
            forms.setdefault(term, word)
    return forms


def similar_work_orders(
    db: Session,
    symptom: str,
    fault_code: str | None,
    equipment_id: int | None = None,
    limit: int = MAX_RELATED,
) -> list[RelatedWorkOrder]:
    """Past work orders that share words (or the fault code) with the report, best match first.

    With ``equipment_id`` only that machine is searched; without it the whole fleet is, because the
    same fault often shows up on sister machines.
    """
    query_text = f"{symptom} {fault_code or ''}"
    query_terms = set(tokenize(query_text))
    forms = _surface_forms(query_text)
    code_terms = set(tokenize(fault_code)) if fault_code else set()
    if not query_terms:
        return []

    stmt = select(WorkOrder)
    if equipment_id is not None:
        stmt = stmt.where(WorkOrder.equipment_id == equipment_id)
    stmt = stmt.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc()).limit(MAX_SCANNED)

    scored: list[tuple[int, WorkOrder, list[str]]] = []
    for wo in db.scalars(stmt):
        shared = query_terms & set(tokenize(f"{wo.title} {wo.description}"))
        if not shared:
            continue
        score = len(shared) + (FAULT_CODE_BONUS if shared & code_terms else 0)
        words = sorted({forms.get(t, t) for t in shared})[:MAX_TERMS]
        scored.append((score, wo, words))

    # Stable sort: equal scores keep the newest-first order from the query.
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        RelatedWorkOrder(
            wo_number=wo.wo_number,
            title=wo.title,
            description=wo.description,
            priority=wo.priority,
            status=wo.status,
            created_at=wo.created_at,
            downtime_hours=wo.downtime_hours,
            matched_terms=terms,
        )
        for _, wo, terms in scored[:limit]
    ]


def gather_context(db: Session, req: TroubleshootRequest, equipment: Equipment | None) -> TroubleshootingContext:
    ctx = TroubleshootingContext(equipment=equipment)
    if not req.include_history:
        return ctx
    if equipment is not None:
        ctx.history = equipment_history(db, equipment)
    ctx.related = similar_work_orders(
        db, req.symptom, req.fault_code, equipment.id if equipment is not None else None
    )
    return ctx


def build_search_query(req: TroubleshootRequest, equipment: Equipment | None) -> str:
    """What to look for in the manuals: the symptom, the code, and what kind of machine it is."""
    parts = [req.symptom]
    if req.fault_code:
        parts.append(req.fault_code)
    if equipment is not None:
        parts += [equipment.name, equipment.type, equipment.manufacturer]
    return " ".join(p for p in parts if p)


def build_question(req: TroubleshootRequest, ctx: TroubleshootingContext) -> str:
    """The question sent to the model: the report plus the context gathered from the database."""
    lines = ["Troubleshooting request."]
    eq = ctx.equipment
    if eq is not None:
        maker = f", {eq.manufacturer}" if eq.manufacturer else ""
        lines.append(f"Equipment: {eq.name} ({eq.tag}), {eq.type}{maker}; location {eq.location}; status {eq.status}.")
    if req.fault_code:
        lines.append(f"Fault code: {req.fault_code}")
    lines.append(f"Symptom: {req.symptom}")
    if ctx.history is not None:
        h = ctx.history
        lines.append(
            f"History: {h.work_orders_total} work orders ({h.work_orders_open} not closed), "
            f"{h.downtime_hours_total:g} h downtime."
        )
    if ctx.related:
        lines.append("Similar past work orders:")
        for wo in ctx.related:
            detail = " ".join(wo.description.split())[:DESCRIPTION_CHARS]
            lines.append(f"- {wo.wo_number} ({wo.status}, {wo.priority}): {wo.title}. {detail}".rstrip())
    lines.append(TASK)
    return "\n".join(lines)