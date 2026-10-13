import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-test-pass-123"; // throwaway local credential for the e2e account

async function register(page: Page) {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/");
  await page.getByRole("button", { name: /Need an account/ }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Conversation" })).toBeVisible();
  return email;
}

async function ask(page: Page, text: string) {
  await page.getByLabel("Command").fill(text);
  await page.getByRole("button", { name: "Send", exact: true }).click();
}

test("submit → plan → approve → verified result → history", async ({ page }) => {
  await register(page);
  await ask(page, "run the tests");
  await expect(page.getByText("Approval required — this has not run.")).toBeVisible();
  await expect(page.getByRole("status", { name: /Needs your approval/ })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/exited with code 0/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/tool ran and its output matched the declared schema/)).toBeVisible();
  await page.getByRole("link", { name: "Tasks" }).click();
  await expect(page.getByText("run the tests").first()).toBeVisible();
  await page.getByRole("link", { name: "Conversations" }).click();
  await expect(page.getByText("run the tests").first()).toBeVisible();
});

test("declining approval never runs the command; cancel works", async ({ page }) => {
  await register(page);
  await ask(page, "run the tests");
  await page.getByRole("button", { name: "Decline" }).click();
  await expect(page.getByText(/declined by user|you declined approval/).first()).toBeVisible();
  await ask(page, "run the tests");
  await page.getByRole("button", { name: "Cancel task" }).click();
  await expect(page.getByText("cancelled").first()).toBeVisible();
});

test("failed task is reported honestly and can be retried", async ({ page }) => {
  await register(page);
  await ask(page, "read does-not-exist.txt");
  await expect(page.getByText("file not found").first()).toBeVisible();
  await page.getByRole("button", { name: "Retry failed steps" }).click();
  await expect(page.getByText("file not found").first()).toBeVisible();
});

test("memory: secrets refused, save, export, delete, disable", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Memory" }).click();
  await page.getByLabel("New memory").fill("my password is hunter2hunter2");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator('main [role="alert"]')).toContainText("not saved");
  await page.getByLabel("New memory").fill("I prefer concise answers");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("I prefer concise answers")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  expect((await download).suggestedFilename()).toBe("jarvis-memories.json");
  await page.getByLabel(/Persistent memory enabled/).uncheck();
  await expect(page.getByText(/Memory is off/)).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("No memories saved.")).toBeVisible();
});

test("knowledge base: upload, cited search, validation error, delete", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Knowledge Base" }).click();
  await page.getByLabel(/Upload a document/).setInputFiles({ name: "falcon.md", mimeType: "text/markdown", buffer: Buffer.from("Project Falcon launches on March 14. The budget owner is Dana.") });
  await expect(page.getByText(/indexed · 1 chunks/)).toBeVisible();
  await page.getByLabel("Search query").fill("when does falcon launch");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText(/\[1\] falcon.md/)).toBeVisible();
  await page.getByLabel(/Upload a document/).setInputFiles({ name: "bad.txt", mimeType: "text/plain", buffer: Buffer.from([0, 1, 2, 3]) });
  await expect(page.locator('main [role="alert"]')).toContainText(/binary/i);
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("No documents yet.")).toBeVisible();
});

test("voice and vision are honest when unconfigured", async ({ page }) => {
  await register(page);
  await page.getByRole("button", { name: /Push to talk/ }).dispatchEvent("pointerdown");
  await expect(page.getByText(/No speech-to-text provider/)).toBeVisible();
  await expect(page.getByText(/No vision model configured/)).toBeVisible();
});

test("signed-out users cannot see the app; mobile layout has no horizontal scroll", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("form", { name: "Sign in" })).toBeVisible();
  await register(page);
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of ["/", "/tasks", "/knowledge", "/memory", "/evals", "/settings", "/tools", "/audit", "/code", "/documents", "/history"]) {
    await page.goto(path);
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
  }
});
