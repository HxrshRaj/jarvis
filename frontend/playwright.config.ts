import { defineConfig } from "@playwright/test";

// Runs against an already-running stack (docker compose up, or the two dev servers).
// Locally you can reuse installed Chrome: E2E_CHANNEL=chrome npx playwright test
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? [["list"], ["github"]] : [["list"]],  // "github" turns failures into PR/check annotations
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    channel: process.env.E2E_CHANNEL || undefined,
    trace: "retain-on-failure",
  },
});
