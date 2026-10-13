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

export const Doc = z.object({ id: z.string(), filename: z.string(), mime: z.string(), size_bytes: z.number(), status: z.string(), error: z.string().nullable(), n_chunks: z.number(), created_at: z.string() });
export const DocText = Doc.extend({ text: z.string(), truncated: z.boolean() });
export const DocHit = z.object({ chunk_id: z.string(), document_id: z.string(), filename: z.string(), chunk_index: z.number(), page: z.number().nullable(), score: z.number(), text: z.string() });
export const Mem = z.object({ id: z.string(), kind: z.string(), content: z.string(), created_at: z.string() });
export const Conv = z.object({ id: z.string(), title: z.string(), created_at: z.string() });
export const Caps = z.object({ llm: z.boolean(), vision: z.boolean(), speech_to_text: z.boolean(), text_to_speech: z.boolean(), router: z.string(), browser_tts_fallback: z.boolean() });
export const ProviderView = z.object({ provider: z.string(), endpoint_host: z.string().nullable(), model: z.string().nullable(), vision_model: z.string().nullable(), stt_model: z.string().nullable(), tts_model: z.string().nullable(), api_key_configured: z.boolean(), how_to_change: z.string() });
export const Usage = z.object({ usage: z.array(z.object({ provider: z.string(), model: z.string(), purpose: z.string(), calls: z.number(), prompt_tokens: z.number(), completion_tokens: z.number(), estimated_cost_usd: z.number().nullable() })), note: z.string() });
export const WsEntry = z.object({ name: z.string(), is_dir: z.boolean(), size: z.number().nullable() });
export const EvalRunT = z.object({ id: z.string(), created_at: z.string().optional(), config: z.record(z.string(), z.unknown()), results: z.record(z.string(), z.any()) });

export type TaskT = z.infer<typeof Task>;
export const TERMINAL = ["succeeded", "failed", "cancelled", "partially_completed"];

async function call<T extends z.ZodTypeAny>(schema: T, path: string, init: RequestInit = {}): Promise<z.infer<T>> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),  // browser sets the multipart boundary
        ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers,
      },
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
async function callVoid(path: string, init: RequestInit): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
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
  conversations: (limit = 50) => call(page(Conv), `/api/v1/conversations?limit=${limit}`),
  deleteConversation: (id: string) => callVoid(`/api/v1/conversations/${id}`, { method: "DELETE" }),
  documents: () => call(page(Doc), "/api/v1/documents?limit=100"),
  uploadDocument: (file: File) => { const f = new FormData(); f.append("file", file); return call(Doc, "/api/v1/documents", { method: "POST", body: f }); },
  deleteDocument: (id: string) => callVoid(`/api/v1/documents/${id}`, { method: "DELETE" }),
  reindexDocument: (id: string) => call(Doc, `/api/v1/documents/${id}/reindex`, post()),
  documentText: (id: string) => call(DocText, `/api/v1/documents/${id}/text`),
  searchDocuments: (query: string) => call(z.object({ hits: z.array(DocHit) }), "/api/v1/documents/search", post({ query, k: 5 })),
  memories: () => call(page(Mem), "/api/v1/memories?limit=200"),
  addMemory: (content: string, kind: string) => call(Mem, "/api/v1/memories", post({ content, kind })),
  editMemory: (id: string, content: string) => call(Mem, `/api/v1/memories/${id}`, { method: "PATCH", body: JSON.stringify({ content }) }),
  deleteMemory: (id: string) => callVoid(`/api/v1/memories/${id}`, { method: "DELETE" }),
  exportMemories: () => call(z.object({ memories: z.array(Mem) }), "/api/v1/memories-export"),
  memorySetting: () => call(z.object({ enabled: z.boolean() }), "/api/v1/settings/memory"),
  setMemorySetting: (enabled: boolean) => call(z.object({ enabled: z.boolean() }), "/api/v1/settings/memory", { method: "PUT", body: JSON.stringify({ enabled }) }),
  capabilities: () => call(Caps, "/api/v1/capabilities"),
  provider: () => call(ProviderView, "/api/v1/settings/provider"),
  usage: () => call(Usage, "/api/v1/usage"),
  workspaceList: (path = ".") => call(z.object({ path: z.string(), entries: z.array(WsEntry) }), `/api/v1/workspace/list?path=${encodeURIComponent(path)}`),
  workspaceFile: (path: string) => call(z.object({ path: z.string(), content: z.string(), truncated: z.boolean() }), `/api/v1/workspace/file?path=${encodeURIComponent(path)}`),
  lookAtThis: (image: File, question: string) => { const f = new FormData(); f.append("image", image); f.append("question", question); return call(z.object({ answer: z.string(), stored: z.boolean(), note: z.string() }), "/api/v1/vision/analyze", { method: "POST", body: f }); },
  transcribe: (audio: Blob) => { const f = new FormData(); f.append("audio", audio, "speech.webm"); return call(z.object({ text: z.string() }), "/api/v1/voice/transcribe", { method: "POST", body: f }); },
  speak: async (text: string): Promise<Blob> => {
    const res = await fetch(`${API_URL}/api/v1/voice/speak`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken() ?? ""}` }, body: JSON.stringify({ text }) });
    if (!res.ok) throw new ApiError(res.status, "Speech synthesis is not available");
    return res.blob();
  },
  runEvals: () => call(EvalRunT, "/api/v1/evals/run", post()),
  evals: () => call(z.object({ runs: z.array(EvalRunT) }), "/api/v1/evals"),
  mlReport: () => call(z.record(z.string(), z.any()), "/api/v1/ml/report"),
};
