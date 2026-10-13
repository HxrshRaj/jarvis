import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getToken, setToken } from "./api";

describe("api client", () => {
  beforeEach(() => { localStorage.clear(); });
  afterEach(() => vi.unstubAllGlobals());

  it("reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    await expect(api.tools()).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/Cannot reach/) });
  });

  it("clears the stored token on 401 and surfaces the server message", async () => {
    setToken("abc");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 })));
    await expect(api.tools()).rejects.toBeInstanceOf(ApiError);
    expect(getToken()).toBeNull();
  });

  it("validates responses against the schema", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{ name: 1 }]), { status: 200 })));
    await expect(api.tools()).rejects.toThrow();
  });

  it("sends the bearer token and does not force a JSON content type for uploads", async () => {
    setToken("tok");
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "d", filename: "a.md", mime: "text/plain", size_bytes: 1, status: "indexed", error: null, n_chunks: 1, created_at: "x" }), { status: 201 }));
    vi.stubGlobal("fetch", f);
    await api.uploadDocument(new File(["x"], "a.md"));
    const init = f.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("falls back gracefully when localStorage throws", () => {
    vi.stubGlobal("localStorage", { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } });
    expect(getToken()).toBeNull();
    expect(() => setToken("x")).not.toThrow();
  });
});
