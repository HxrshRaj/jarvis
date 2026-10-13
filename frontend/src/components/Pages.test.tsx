import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import KnowledgePage from "@/app/knowledge/page";
import MemoryPage from "@/app/memory/page";
import { LookAtThis } from "./LookAtThis";

const m = vi.hoisted(() => ({
  documents: vi.fn(), uploadDocument: vi.fn(), deleteDocument: vi.fn(), searchDocuments: vi.fn(),
  memories: vi.fn(), memorySetting: vi.fn(), addMemory: vi.fn(), setMemorySetting: vi.fn(), editMemory: vi.fn(), deleteMemory: vi.fn(), exportMemories: vi.fn(),
  lookAtThis: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), api: m }));

const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
const file = (name: string, type: string, size = 10) => new File([new Uint8Array(size)], name, { type });

beforeEach(() => {
  vi.clearAllMocks();
  m.documents.mockResolvedValue({ items: [], total: 0 });
  m.memories.mockResolvedValue({ items: [{ id: "m1", kind: "preference", content: "I like tea", created_at: "2026-01-01T00:00:00Z" }], total: 1 });
  m.memorySetting.mockResolvedValue({ enabled: true });
});

describe("Knowledge page", () => {
  it("uploads a file and surfaces backend validation errors", async () => {
    m.uploadDocument.mockRejectedValue(new Error("supported types: PDF, TXT, MD, CSV, LOG, RST"));
    wrap(<KnowledgePage />);
    const input = await screen.findByLabelText(/Upload a document/);
    fireEvent.change(input, { target: { files: [file("a.exe", "application/octet-stream")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/supported types/);
    expect(m.uploadDocument).toHaveBeenCalledTimes(1);
  });

  it("shows a clear empty-result message and cited hits", async () => {
    m.searchDocuments.mockResolvedValueOnce({ hits: [] }).mockResolvedValueOnce({
      hits: [{ chunk_id: "c1", document_id: "d1", filename: "falcon.md", chunk_index: 0, page: 2, score: 1, text: "Launch is March 14." }] });
    wrap(<KnowledgePage />);
    const box = await screen.findByLabelText("Search query");
    fireEvent.change(box, { target: { value: "launch" } });
    fireEvent.submit(box.closest("form")!);
    expect(await screen.findByText(/Nothing relevant found/)).toBeInTheDocument();
    fireEvent.submit(box.closest("form")!);
    expect(await screen.findByText(/falcon.md/)).toBeInTheDocument();
    expect(screen.getByText(/p\.2/)).toBeInTheDocument();
  });
});

describe("Memory page", () => {
  it("shows the secret-refusal message from the backend and does not clear the input", async () => {
    m.addMemory.mockRejectedValue(new Error("This looks like a password, key, token or other sensitive identifier; it was not saved."));
    wrap(<MemoryPage />);
    const input = await screen.findByLabelText("New memory");
    fireEvent.change(input, { target: { value: "my password is hunter2hunter2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not saved/);
    expect(input).toHaveValue("my password is hunter2hunter2");
  });

  it("can disable persistent memory and warns about it", async () => {
    m.setMemorySetting.mockResolvedValue({ enabled: false });
    wrap(<MemoryPage />);
    const box = await screen.findByLabelText(/Persistent memory enabled/);
    m.memorySetting.mockResolvedValue({ enabled: false });
    fireEvent.click(box);
    await waitFor(() => expect(m.setMemorySetting).toHaveBeenCalledWith(false));
    expect(await screen.findByText(/Memory is off/)).toBeInTheDocument();
  });

  it("deletes after confirmation only", async () => {
    m.deleteMemory.mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    wrap(<MemoryPage />);
    const del = await screen.findByRole("button", { name: "Delete" });
    fireEvent.click(del);
    expect(m.deleteMemory).not.toHaveBeenCalled();
    fireEvent.click(del);
    await waitFor(() => expect(m.deleteMemory).toHaveBeenCalledWith("m1"));
    confirm.mockRestore();
  });
});

describe("LookAtThis", () => {
  it("rejects unsupported and oversized images before any upload", async () => {
    wrap(<LookAtThis available />);
    const input = screen.getByLabelText("Image");
    fireEvent.change(input, { target: { files: [file("a.pdf", "application/pdf")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/PNG, JPEG, GIF or WebP/);
    fireEvent.change(input, { target: { files: [file("big.png", "image/png", 5 * 1024 * 1024 + 1)] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/5 MB/);
    expect(screen.getByRole("button", { name: /Analyse image/ })).toBeDisabled();
    expect(m.lookAtThis).not.toHaveBeenCalled();
  });

  it("warns when no vision model is configured and shows the backend's unavailable error", async () => {
    m.lookAtThis.mockRejectedValue(new Error("no vision-capable provider is configured"));
    wrap(<LookAtThis available={false} />);
    expect(screen.getByText(/No vision model configured/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Image"), { target: { files: [file("s.png", "image/png")] } });
    fireEvent.click(await screen.findByRole("button", { name: /Analyse image/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/no vision-capable provider/);
  });

  it("shows the answer with the verification caveat", async () => {
    m.lookAtThis.mockResolvedValue({ answer: "A TypeError on line 4.", stored: false, note: "verify important details" });
    wrap(<LookAtThis available />);
    fireEvent.change(screen.getByLabelText("Image"), { target: { files: [file("s.png", "image/png")] } });
    fireEvent.click(await screen.findByRole("button", { name: /Analyse image/ }));
    expect(await screen.findByText(/TypeError on line 4/)).toBeInTheDocument();
    expect(screen.getByText(/verify important details/)).toBeInTheDocument();
  });
});
