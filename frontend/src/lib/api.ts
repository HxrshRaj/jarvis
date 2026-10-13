import { z } from "zod";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "jarvis.token";

// Session token lives in localStorage (documented trade-off: XSS-readable; see docs/SECURITY.md).
export const getToken = (): string | null => {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
};
export const setToken = (t: string | null) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const Step = z.object({
  id: z.string(), index: z.number(), tool: z.string(), description: z.string(),
  args: z.record(z.string(), z.unknown()), risk: z.string(), requires_approval: z.boolean(),
  approved: z.boolean(), status: z.string(), attempts: z.number(),
  output: z.record(z.string(), z.unknown()).nullable(), error: z.string().nullable(),
});
export const Task = z.object({
  id: z.string(), conversation_id: z.string().nullable(), request: z.string(), route: z.string(),
  status: z.string(), success_criteria: z.array(z.string()), summary: z.string().nullable(),
  verification: z.record(z.string(), z.unknown()).nullable(), error: z.string().nullable(),
  created_at: z.string(), steps: z.array(Step),
});
export const TaskItem = z.object({ id: z.string(), request: z.string(), route: z.string(), status: z.string(), created_at: z.string() });
export const Message = z.object({ id: z.string(), role: z.string(), content: z.string(), task_id: z.string().nullable(), created_at: z.string() });
export const Conversation = z.object({ id: z.string(), title: z.string(), messages: z.array(Message) });
export const Tool = z.object({
  name: z.string(), description: z.string(), permissions: z.array(z.string()), risk: z.string(),
  timeout: z.number(), max_retries: z.number(), requires_approval: z.boolean(), available: z.boolean(),
});
export const Audit = z.object({ id: z.string(), action: z.string(), resource: z.string(), outcome: z.string(), detail: z.record(z.string(), z.unknown()), created_at: z.string() });
export const Ready = z.object({ database: z.boolean(), llm_provider: z.string(), llm_is_real: z.boolean(), workspace: z.string() });
const page = <T extends z.ZodTypeAny>(item: T) => z.object({ items: z.array(item), total: z.number() });

export type TaskT = z.infer<typeof Task>;
export const TERMINAL = ["succeeded", "failed", "cancelled", "partially_completed"];

async function call<T extends z.ZodTypeAny>(schema: T, path: string, init: RequestInit = {}): Promise<z.infer<T>> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the JARVIS backend. Is it running?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); if (typeof j.detail === "string") detail = j.detail; else if (Array.isArray(j.detail)) detail = "Invalid input"; } catch { /* non-JSON */ }
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, detail);
  }
  return schema.parse(await res.json());
}
const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  auth: (mode: "login" | "register", email: string, password: string) =>
    call(z.object({ access_token: z.string() }), `/api/v1/auth/${mode}`, post({ email, password })),
  chat: (message: string, conversation_id?: string) =>
    call(z.object({ conversation_id: z.string(), task_id: z.string() }), "/api/v1/chat", post({ message, conversation_id, idempotency_key: crypto.randomUUID() })),
  task: (id: string) => call(Task, `/api/v1/tasks/${id}`),
  tasks: (limit = 20, offset = 0) => call(page(TaskItem), `/api/v1/tasks?limit=${limit}&offset=${offset}`),
  conversation: (id: string) => call(Conversation, `/api/v1/conversations/${id}`),
  cancel: (id: string) => call(Task, `/api/v1/tasks/${id}/cancel`, post()),
  retry: (id: string) => call(Task, `/api/v1/tasks/${id}/retry`, post()),
  decide: (taskId: string, stepId: string, approve: boolean) =>
    call(Task, `/api/v1/tasks/${taskId}/steps/${stepId}/${approve ? "approve" : "reject"}`, post()),
  tools: () => call(z.array(Tool), "/api/v1/tools"),
  audit: (limit = 50) => call(page(Audit), `/api/v1/audit?limit=${limit}`),
  ready: () => call(Ready, "/health/ready"),
};
