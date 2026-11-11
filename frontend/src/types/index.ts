/**
 * Shapes of the backend API (mirror backend/app/schemas.py).
 * Dates arrive as ISO strings: "YYYY-MM-DD" for dates, a full timestamp for date-times.
 */

export type EquipmentStatus = "operational" | "maintenance" | "fault" | "retired";
export type Priority = "low" | "medium" | "high" | "critical";
export type WorkOrderStatus = "open" | "in_progress" | "closed";
export type RetrievalMode = "keyword" | "semantic" | "hybrid";

export interface Equipment {
  id: number;
  tag: string;
  name: string;
  type: string;
  location: string;
  manufacturer: string;
  status: EquipmentStatus;
}

export interface WorkOrder {
  id: number;
  wo_number: string;
  equipment_id: number;
  title: string;
  description: string;
  priority: Priority;
  status: WorkOrderStatus;
  technician: string;
  created_at: string;
  downtime_hours: number;
}

export interface DocumentInfo {
  id: number;
  filename: string;
  pages: number;
  chunks: number;
  uploaded_at: string;
}

export interface Source {
  document: string;
  page: number;
  excerpt: string;
  score: number;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  retrieval_mode: RetrievalMode;
  generated_by: string;
  latency_ms: number;
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  uptime_seconds: number;
  database: boolean;
  semantic_search: boolean;
  gemini_configured: boolean;
  indexed_chunks: number;
}

export interface EquipmentDowntime {
  tag: string;
  name: string;
  hours: number;
  work_orders: number;
}

export interface MonthlyWorkOrders {
  month: string; // "YYYY-MM"
  work_orders: number;
  downtime_hours: number;
}

export interface AnalyticsSummary {
  equipment_total: number;
  equipment_by_status: Record<string, number>;
  work_orders_total: number;
  work_orders_open: number;
  work_orders_by_status: Record<string, number>;
  work_orders_by_priority: Record<string, number>;
  downtime_hours_total: number;
  downtime_by_equipment: EquipmentDowntime[];
  work_orders_by_month: MonthlyWorkOrders[];
  documents: number;
  pages: number;
  passages: number;
  document_stats: DocumentStat[];
}

export interface DocumentStat {
  filename: string;
  pages: number;
  passages: number;
  uploaded_at: string;
}

export interface Passage {
  document: string;
  page: number;
  chunk_index: number;
  text: string;
  score: number | null;
}

export interface KnowledgeStats {
  documents: number;
  pages: number;
  passages: number;
  indexed_vectors: number;
  semantic_enabled: boolean;
  embedding_model: string;
}

export interface DocumentSummary {
  answer: string;
  generated_by: string;
  passages_used: number;
  latency_ms: number;
}

export interface EquipmentHistory {
  work_orders_total: number;
  work_orders_open: number;
  downtime_hours_total: number;
  last_work_order_date: string | null;
}

export interface RelatedWorkOrder {
  wo_number: string;
  title: string;
  description: string;
  priority: Priority;
  status: WorkOrderStatus;
  created_at: string;
  downtime_hours: number;
  matched_terms: string[];
}

export interface TroubleshootRequest {
  symptom: string;
  equipment_tag?: string | null;
  fault_code?: string | null;
  include_history?: boolean;
  top_k?: number;
}

export interface TroubleshootResponse {
  answer: string;
  equipment: Equipment | null;
  history: EquipmentHistory | null;
  related_work_orders: RelatedWorkOrder[];
  sources: Source[];
  retrieval_mode: RetrievalMode;
  generated_by: string;
  latency_ms: number;
}

export interface EquipmentCreate {
  tag: string;
  name: string;
  type?: string;
  location?: string;
  manufacturer?: string;
  status?: EquipmentStatus;
}

export type Role = "admin" | "technician";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface UserCreate {
  email: string;
  name?: string;
  role: Role;
  password: string;
}

export interface UserUpdate {
  name?: string;
  role?: Role;
  is_active?: boolean;
  password?: string;
}

export type EquipmentUpdate = Partial<Omit<EquipmentCreate, "tag">>;

export interface WorkOrderUpdate {
  title?: string;
  description?: string;
  priority?: Priority;
  status?: WorkOrderStatus;
  technician?: string;
  downtime_hours?: number;
}

export interface ImportResult {
  added: number;
  skipped: number;
  errors: string[];
}

/** Upload response: the document plus the machine added to the registry for it (null if it already existed). */
export interface DocumentUploaded extends DocumentInfo {
  registered_equipment: Equipment | null;
}

export interface WorkOrderCreate {
  equipment_id: number;
  title: string;
  description?: string;
  priority?: Priority;
  technician?: string;
  downtime_hours?: number;
}

/** The uniform error body every failed request returns. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id?: string | null;
    details?: Array<Record<string, unknown>> | null;
  };
}

/** One page of a list plus the total number of matches (from the X-Total-Count header). */
export interface Page<T> {
  items: T[];
  total: number;
}