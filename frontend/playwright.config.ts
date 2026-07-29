import { defineConfig } from "@playwright/test";
import path from "node:path";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `${path.resolve("../.venv/Scripts/python.exe")} -m elite_logistics.main`,
    cwd: "..",
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      ...process.env,
      ELITE_LOGISTICS_DATA_DIR: path.resolve("../build/e2e-data"),
      ELITE_LOGISTICS_OPEN_BROWSER: "0",
    },
  },
});
