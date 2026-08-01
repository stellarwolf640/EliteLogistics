import { expect, test, type Page } from "@playwright/test";

const leg = {
  source_market_id: 1, source_station: "Galileo", source_system_id64: 10, source_system: "Sol",
  destination_market_id: 2, destination_station: "Mercator Port", destination_system_id64: 20, destination_system: "Waypoint",
  commodity_id: 100, commodity: "Silver", buy_price: 10000, sell_price: 23000, quantity: 100,
  profit_per_ton: 13000, trip_profit: 1300000, system_distance_ly: 20, jumps: 2,
  estimated_seconds: 300, credits_per_hour: 15600000, distance_to_route_ly: 0, relocation_jumps: 0,
  relocation_seconds: 0, first_trip_credits_per_hour: 15600000, confidence_score: 91, confidence: "High",
  source_observed_at: "2026-07-29T16:00:00Z", destination_observed_at: "2026-07-29T16:00:00Z",
  provider: "fixture", warnings: [],
};

async function seedLocation(page: Page) {
  const preferences = await page.request.get("/api/preferences").then((value) => value.json());
  preferences.search_draft.origin_system_id64 = "10";
  preferences.search_draft.origin_station_market_id = "1";
  preferences.search_draft.origin_location_label = "Galileo, Sol";
  preferences.search_draft.destination_system_id64 = "20";
  preferences.search_draft.destination_station_market_id = "2";
  preferences.search_draft.destination_location_label = "Mercator Port, Waypoint";
  await page.request.put("/api/preferences", { data: preferences });
}

test("creates and restores a Type-6 ship profile", async ({ page }) => {
  const profiles = await page.request.get("/api/ship-profiles").then((value) => value.json());
  for (const profile of profiles.filter((value: { name: string }) => value.name === "E2E Type-6")) {
    await page.request.delete(`/api/ship-profiles/${profile.id}`);
  }
  await page.goto("/ships");
  await page.getByLabel("Profile name").fill("E2E Type-6");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByRole("heading", { name: "E2E Type-6" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "E2E Type-6" })).toBeVisible();
});

test("finds a one-way trade and opens its manifest", async ({ page }) => {
  await seedLocation(page);
  await page.route("**/api/trades/search", (route) => route.fulfill({ json: { routes: [leg], available_credits: 11650000, assumptions: [] } }));
  await page.goto("/trade");
  await page.getByRole("button", { name: "Find trades" }).click();
  await expect(page.getByText("Silver · 100 t")).toBeVisible();
  await page.getByRole("button", { name: "Open flight board" }).click();
  await expect(page.getByText("100 t · Silver")).toBeVisible();
});

test("finds a profitable closed loop", async ({ page }) => {
  await seedLocation(page);
  const returning = { ...leg, source_market_id: 2, source_station: "Mercator Port", source_system_id64: 20, source_system: "Waypoint", destination_market_id: 1, destination_station: "Galileo", destination_system_id64: 10, destination_system: "Sol", commodity_id: 101, commodity: "Consumer Technology" };
  await page.route("**/api/round-trips/search", (route) => route.fulfill({ json: { routes: [{ outbound: leg, return_leg: returning, total_profit: 2600000, estimated_seconds: 600, relocation_seconds: 0, credits_per_hour: 15600000, confidence: "High" }], available_credits: 11650000, assumptions: [] } }));
  await page.goto("/round-trips");
  await page.getByRole("button", { name: "Find round trips" }).click();
  await expect(page.getByText("Consumer Technology · 100 t")).toBeVisible();
});

test("compares direct, fast, balanced, and profit transit plans", async ({ page }) => {
  await seedLocation(page);
  await page.route("**/api/transit/plans", (route) => route.fulfill({ status: 202, json: { job_id: "fixture-job", status: "queued" } }));
  const summary = (profile: string, profit: number) => ({ profile, legs: profile === "Direct" ? [] : [leg], total_distance_ly: 250, estimated_jumps: 12, estimated_seconds: 1200, expected_profit: profit, extra_seconds_vs_direct: profile === "Direct" ? 0 : 300, extra_distance_vs_direct: 0, confidence: "High", positioning_station: null, positioning_system: null, warnings: [] });
  await page.route("**/api/jobs/fixture-job", (route) => route.fulfill({ json: { id: "fixture-job", kind: "transit", status: "complete", progress: 1, result: { direct: summary("Direct", 0), options: [summary("Fast", 500000), summary("Balanced", 900000), summary("Profit", 1400000)] }, error: null } }));
  await page.goto("/transit");
  await page.getByRole("button", { name: "Plan profitable transit" }).click();
  for (const profile of ["Direct", "Fast", "Balanced", "Profit"]) await expect(page.getByText(`${profile} route`, { exact: true })).toBeVisible();
});

test("configures Computer and runs one audited safe tool", async ({ page }) => {
  await page.goto("/computer");
  await expect(page.getByRole("heading", { name: "Computer command and control." })).toBeVisible();
  await expect(page.getByText(/Game input remains disabled/i)).toBeVisible();

  await page.getByLabel("Operating mode").selectOption("command");
  await page.getByLabel("Computer command").fill("Where am I?");
  await page.getByRole("button", { name: "Execute" }).click();
  await expect(page.getByText(/Current location:/i)).toBeVisible();

  const snapshot = page.locator(".computer-tools article").filter({ hasText: "get operational snapshot" });
  await expect(snapshot.getByRole("button", { name: "Run" })).toBeEnabled();
  await snapshot.getByRole("button", { name: "Run" }).click();

  await expect(page.getByText("Latest invocation")).toBeVisible();
  await expect(page.locator(".computer-result")).toContainText("completed");
  await expect(page.getByRole("heading", { name: "Elite control bindings" })).toBeVisible();
  await expect(page.getByText(/Elite must be foreground/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Gear down" })).toBeDisabled();
});
