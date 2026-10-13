import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TaskPanel } from "./TaskPanel";

const base = {
  id: "t1", conversation_id: "c1", request: "run the tests", route: "coding_assistance", success_criteria: [],
  summary: null, verification: { plan_source: "rules" }, error: null, created_at: "2026-01-01T00:00:00Z",
};
const step = { id: "s1", index: 0, tool: "run_command", description: "Run pytest", args: { argv: ["pytest"] }, risk: "low",
  requires_approval: true, approved: false, attempts: 0, output: null, error: null };

const { decide, cancel, task } = vi.hoisted(() => ({ decide: vi.fn(), cancel: vi.fn(), task: vi.fn() }));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), api: { task, decide, cancel, retry: vi.fn() } }));

const wrap = () => render(
  <QueryClientProvider client={new QueryClient()}><TaskPanel taskId="t1" /></QueryClientProvider>);

describe("TaskPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows an approval gate and sends the decision", async () => {
    task.mockResolvedValue({ ...base, status: "awaiting_approval", steps: [{ ...step, status: "awaiting_approval" }] });
    decide.mockResolvedValue({ ...base, status: "running", steps: [{ ...step, status: "pending", approved: true }] });
    wrap();
    expect(await screen.findByText(/has not run/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(decide).toHaveBeenCalledWith("t1", "s1", true));
  });

  it("offers cancel while active but not after completion", async () => {
    task.mockResolvedValue({ ...base, status: "running", steps: [{ ...step, status: "running" }] });
    const { unmount } = wrap();
    fireEvent.click(await screen.findByRole("button", { name: "Cancel task" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("t1"));
    unmount();
    task.mockResolvedValue({ ...base, status: "succeeded", steps: [{ ...step, status: "succeeded" }] });
    wrap();
    await screen.findAllByText("succeeded");
    expect(screen.queryByRole("button", { name: "Cancel task" })).toBeNull();
  });

  it("surfaces failures and offers retry", async () => {
    task.mockResolvedValue({ ...base, status: "failed", steps: [{ ...step, status: "failed", error: "file not found" }] });
    wrap();
    expect(await screen.findByText("file not found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry failed steps" })).toBeInTheDocument();
  });
});
