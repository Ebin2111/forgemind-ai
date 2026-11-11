"""Pydantic request/response models (the public API contract)."""
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .core.security import EMAIL_PATTERN, password_problem

EquipmentStatus = Literal["operational", "maintenance", "fault", "retired"]
Priority = Literal["low", "medium", "high", "critical"]
WorkOrderStatus = Literal["open", "in_progress", "closed"]
RetrievalMode = Literal["keyword", "semantic", "hybrid"]
Role = Literal["admin", "technician"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- registry ---------------------------------------------------------------
class EquipmentOut(ORMModel):
    id: int
    tag: str
    name: str
    type: str
    location: str
    manufacturer: str
    status: str


class WorkOrderOut(ORMModel):
    id: int
    wo_number: str
    equipment_id: int
    title: str
    description: str
    priority: str
    status: str
    technician: str
    created_at: date
    downtime_hours: float


class EquipmentCreate(BaseModel):
    """Add a machine to the registry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    tag: str = Field(min_length=1, max_length=50, description="Unique asset tag, e.g. CMP-201")
    name: str = Field(min_length=2, max_length=200)
    type: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=200)
    manufacturer: str = Field(default="", max_length=100)
    status: EquipmentStatus = "operational"


class EquipmentUpdate(BaseModel):
    """Change any of these fields; fields that are left out stay as they are."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    type: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)
    manufacturer: Optional[str] = Field(default=None, max_length=100)
    status: Optional[EquipmentStatus] = None


class WorkOrderUpdate(BaseModel):
    """Change any of these fields; fields that are left out stay as they are."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    priority: Optional[Priority] = None
    status: Optional[WorkOrderStatus] = None
    technician: Optional[str] = Field(default=None, max_length=100)
    downtime_hours: Optional[float] = Field(default=None, ge=0, le=100000)


class ImportResult(BaseModel):
    added: int
    skipped: int
    errors: list[str] = Field(default_factory=list, description="Up to 20 reasons rows were skipped")


# --- documents --------------------------------------------------------------
class WorkOrderCreate(BaseModel):
    """Raise a new work order. The number, status and date are set by the server."""

    model_config = ConfigDict(str_strip_whitespace=True)

    equipment_id: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)
    priority: Priority = "medium"
    technician: str = Field(default="", max_length=100)
    downtime_hours: float = Field(default=0, ge=0, le=100000)


class DocumentOut(ORMModel):
    id: int
    filename: str
    pages: int
    chunks: int
    uploaded_at: datetime


class DocumentUploaded(DocumentOut):
    """Upload response: the document, plus the machine that was added to the registry for it (if any)."""

    registered_equipment: Optional[EquipmentOut] = None


class DeleteOut(BaseModel):
    deleted: str


class DocumentSummary(BaseModel):
    answer: str
    generated_by: str
    passages_used: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


# --- assistant --------------------------------------------------------------
class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=2, max_length=1000, description="Natural-language question")
    top_k: Optional[int] = Field(default=None, ge=1, le=10, description="Passages to retrieve")

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v


class Source(BaseModel):
    document: str
    page: int = Field(ge=1)
    excerpt: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    retrieval_mode: RetrievalMode
    generated_by: str
    latency_ms: int


# --- troubleshooting --------------------------------------------------------
# Equipment tags ("P-101") and fault codes ("E-204", "F0003") are short identifiers;
# restricting the alphabet keeps them safe to log and to use in search and SQL filters.
_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"


class TroubleshootRequest(BaseModel):
    """A fault report: what is wrong, optionally on which machine and with which fault code."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "symptom": "Pump vibrates heavily and the bearing housing is hot",
                    "equipment_tag": "P-101",
                    "fault_code": "E-204",
                    "include_history": True,
                    "top_k": 5,
                }
            ]
        },
    )

    symptom: str = Field(
        min_length=3, max_length=1000, description="What the operator observes, in plain language"
    )
    equipment_tag: Optional[str] = Field(
        default=None,
        max_length=50,
        pattern=_CODE_PATTERN,
        description="Equipment tag from the registry, e.g. P-101. Adds machine details and history.",
    )
    fault_code: Optional[str] = Field(
        default=None,
        max_length=50,
        pattern=_CODE_PATTERN,
        description="Controller or alarm code shown on the machine, e.g. E-204",
    )
    include_history: bool = Field(
        default=True, description="Use this machine's earlier work orders as extra context"
    )
    top_k: Optional[int] = Field(default=None, ge=1, le=10, description="Passages to retrieve")

    @field_validator("equipment_tag", "fault_code", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        """Forms often send "" for an empty optional box; treat it as not provided."""
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("symptom")
    @classmethod
    def _symptom_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("symptom must not be blank")
        return v


class EquipmentHistory(BaseModel):
    """Maintenance summary for the machine in the report."""

    work_orders_total: int = Field(ge=0)
    work_orders_open: int = Field(ge=0, description="Work orders that are not closed")
    downtime_hours_total: float = Field(ge=0)
    last_work_order_date: Optional[date] = None


class RelatedWorkOrder(ORMModel):
    """An earlier work order that resembles the reported fault."""

    wo_number: str
    title: str
    description: str
    priority: str
    status: str
    created_at: date
    downtime_hours: float
    matched_terms: list[str] = Field(
        default_factory=list, description="Words shared with the symptom or fault code"
    )


class TroubleshootResponse(BaseModel):
    answer: str
    equipment: Optional[EquipmentOut] = Field(
        default=None, description="Set when equipment_tag matched the registry"
    )
    history: Optional[EquipmentHistory] = None
    related_work_orders: list[RelatedWorkOrder] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    retrieval_mode: RetrievalMode
    generated_by: str
    latency_ms: int = Field(ge=0)


# --- analytics --------------------------------------------------------------
class EquipmentDowntime(BaseModel):
    tag: str
    name: str
    hours: float
    work_orders: int


class MonthlyWorkOrders(BaseModel):
    month: str = Field(description="YYYY-MM")
    work_orders: int
    downtime_hours: float


class DocumentStat(BaseModel):
    filename: str
    pages: int
    passages: int
    uploaded_at: datetime


class AnalyticsSummary(BaseModel):
    equipment_total: int
    equipment_by_status: dict[str, int]
    work_orders_total: int
    work_orders_open: int = Field(description="Work orders that are not closed")
    work_orders_by_status: dict[str, int]
    work_orders_by_priority: dict[str, int]
    downtime_hours_total: float
    downtime_by_equipment: list[EquipmentDowntime]
    work_orders_by_month: list[MonthlyWorkOrders]
    documents: int
    pages: int
    passages: int
    document_stats: list[DocumentStat] = Field(default_factory=list, description="Newest uploads first")


# --- knowledge base ---------------------------------------------------------
class PassageOut(BaseModel):
    document: str
    page: int
    chunk_index: int
    text: str
    score: Optional[float] = None


class KnowledgeStats(BaseModel):
    documents: int
    pages: int
    passages: int
    indexed_vectors: int
    semantic_enabled: bool
    embedding_model: str


# --- sign-in ----------------------------------------------------------------
class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)
    remember: bool = False


class SessionOut(BaseModel):
    email: str
    name: str = ""
    role: Role = "admin"
    auth_required: bool = Field(description="False when the server runs with AUTH_ENABLED=false")


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


# --- user accounts ----------------------------------------------------------
class UserOut(ORMModel):
    id: int
    email: str
    name: str
    role: Role
    is_active: bool
    created_at: datetime


def _check_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not EMAIL_PATTERN.match(value):
        raise ValueError("Enter a valid email address.")
    return value


def _check_password(value: str) -> str:
    problem = password_problem(value)
    if problem:
        raise ValueError(problem)
    return value


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    name: str = Field(default="", max_length=100)
    role: Role = "technician"
    password: str

    _email = field_validator("email")(_check_email)
    _password = field_validator("password")(_check_password)


class UserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, max_length=100)
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None  # set a new password for the person

    _password = field_validator("password")(lambda v: v if v is None else _check_password(v))


# --- system -----------------------------------------------------------------
class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    uptime_seconds: float
    database: bool
    semantic_search: bool
    gemini_configured: bool
    indexed_chunks: int


class LivenessOut(BaseModel):
    status: Literal["alive"]
    uptime_seconds: float


class ComponentCheck(BaseModel):
    name: str
    ok: bool
    latency_ms: float
    detail: Optional[str] = None


class ReadinessOut(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: list[ComponentCheck]


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: Optional[str] = None
    details: Optional[list[dict[str, Any]]] = None


class ErrorResponse(BaseModel):
    error: ErrorBody