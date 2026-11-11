import type {
  AnalyticsSummary, ApiErrorBody, AskResponse, DocumentInfo, DocumentSummary, DocumentUploaded, Equipment, EquipmentCreate, EquipmentUpdate, Health, ImportResult, KnowledgeStats,
  Page, Passage, TroubleshootRequest, TroubleshootResponse, User, UserCreate, UserUpdate, WorkOrder, WorkOrderCreate, WorkOrderUpdate,
} from "@/types";

import { API_BASE as BASE } from "@/lib/config";

type Params = Record<string, string | number | boolean | null | undefined>;

/** "?a=1&b=2" from the given values; empty, null and undefined values are left out. */
function qs(params: Params = {}): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") q.set(key, String(value));
  }
  const text = q.toString();
  return text ? `?${text}` : "";
}

const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

async function send(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, { ...init, credentials: "include" }); // sends the session cookie
  if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    // The session ended (expired or signed out elsewhere): go to the login page and come back afterwards.
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
    throw new Error("Your session has ended. Please sign in again.");
  }
  if (!res.ok) {
    let message = res.statusText || `Request failed (HTTP ${res.status})`;
    try {
      const body = (await res.json()) as Partial<ApiErrorBody> & { detail?: unknown };
      message = body?.error?.message ?? (body?.detail as string | undefined) ?? message;
      const first = body?.error?.details?.[0];
      if (first) message += ` (${String(first.field)}: ${String(first.message)})`;
    } catch {
      // The body was not JSON (for example a proxy error page); keep the status text.
    }
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>;
}

async function page<T>(path: string): Promise<Page<T>> {
  const res = await send(path);
  const items = (await res.json()) as T[];
  return { items, total: Number(res.headers.get("X-Total-Count") ?? items.length) };
}

function importFile(path: string, file: File): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  return request<ImportResult>(path, { method: "POST", body: form });
}

export const api = {
  health: () => request<Health>("/api/health"),
  analytics: () => request<AnalyticsSummary>("/api/analytics/summary"),

  // equipment and maintenance
  equipment: () => request<Equipment[]>("/api/equipment"),
  equipmentPage: (p: { status?: string; limit?: number; offset?: number } = {}) => page<Equipment>(`/api/equipment${qs(p)}`),
  maintenance: () => request<WorkOrder[]>("/api/maintenance"),
  workOrders: (p: { status?: string; priority?: string; equipment_id?: number; q?: string; limit?: number; offset?: number }) =>
    page<WorkOrder>(`/api/maintenance${qs(p)}`),
  createWorkOrder: (body: WorkOrderCreate) => request<WorkOrder>("/api/maintenance", json(body)),
  updateWorkOrder: (id: number, body: WorkOrderUpdate) => request<WorkOrder>(`/api/maintenance/${id}`, json(body, "PATCH")),
  deleteWorkOrder: (id: number) => request<{ deleted: string }>(`/api/maintenance/${id}`, { method: "DELETE" }),
  createEquipment: (body: EquipmentCreate) => request<Equipment>("/api/equipment", json(body)),
  updateEquipment: (id: number, body: EquipmentUpdate) => request<Equipment>(`/api/equipment/${id}`, json(body, "PATCH")),
  deleteEquipment: (id: number) => request<{ deleted: string }>(`/api/equipment/${id}`, { method: "DELETE" }),
  importEquipment: (file: File) => importFile("/api/import/equipment", file),
  importWorkOrders: (file: File) => importFile("/api/import/work-orders", file),

  // documents and knowledge base
  documents: () => request<DocumentInfo[]>("/api/documents"),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentUploaded>("/api/documents/upload", { method: "POST", body: form });
  },
  deleteDocument: (id: number) => request<{ deleted: string }>(`/api/documents/${id}`, { method: "DELETE" }),
  reindexDocument: (id: number) => request<DocumentInfo>(`/api/documents/${id}/reindex`, { method: "POST" }),
  summarizeDocument: (id: number) => request<DocumentSummary>(`/api/documents/${id}/summary`, { method: "POST" }),
  downloadUrl: (id: number) => `${BASE}/api/documents/${id}/download`,
  knowledgeStats: () => request<KnowledgeStats>("/api/knowledge/stats"),
  passages: (p: { document?: string; q?: string; limit?: number; offset?: number }) =>
    page<Passage>(`/api/knowledge/passages${qs(p)}`),

  // user accounts (administrators) and my own password
  users: () => request<User[]>("/api/users"),
  createUser: (body: UserCreate) => request<User>("/api/users", json(body)),
  updateUser: (id: number, body: UserUpdate) => request<User>(`/api/users/${id}`, json(body, "PATCH")),
  deleteUser: (id: number) => request<{ deleted: string }>(`/api/users/${id}`, { method: "DELETE" }),
  changePassword: async (current_password: string, new_password: string) => {
    await send("/api/auth/change-password", json({ current_password, new_password }));
  },

  // assistant
  ask: (question: string) => request<AskResponse>("/api/ask", json({ question })),
  troubleshoot: (body: TroubleshootRequest) => request<TroubleshootResponse>("/api/troubleshoot", json(body)),

  docsUrl: `${BASE}/docs`,
};