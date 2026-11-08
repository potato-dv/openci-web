import { test, expect, type Page } from "@playwright/test";

const sampleUser = { id: 1, name: "Jamie Cruz", email: "jamie@example.test", role: "supervisor", is_active: true };
const sampleAgent = { id: 2, name: "Alex Reyes", email: "alex@example.test", role: "agent", is_active: true };
const sampleAdmin = { id: 3, name: "Morgan Santos", email: "morgan@example.test", role: "admin", is_active: true };
const sampleCases = Array.from({ length: 5 }, (_, index) => ({
  id: index + 1,
  reference_number: `INV-2026-000${index + 1}`,
  first_name: "Fictional",
  middle_name: null,
  last_name: `Subject ${index + 1}`,
  subject_name: `Fictional Subject ${index + 1}`,
  address_display: `${20 + index} Example Road, Diliman, Quezon City`,
  legacy_address: null,
  house_number: String(20 + index),
  street: "Example Road",
  region_code: "1300000000",
  province_code: null,
  city_municipality_code: "1374040000",
  barangay_code: "1374040010",
  priority: index === 0 ? "urgent" : index === 1 ? "high" : "normal",
  status: ["pending", "assigned", "in_progress", "under_review", "completed"][index],
  assigned_agent_id: index === 0 ? null : 2,
  assigned_agent_name: index === 0 ? null : sampleAgent.name,
  location_confirmed: true,
  created_at: "2026-11-04T01:00:00Z",
  updated_at: "2026-11-04T01:00:00Z",
  service_duration_seconds: 2700,
  latitude: 14.65 + index * 0.01,
  longitude: 121.06 + index * 0.01,
}));
const permissionFeatures = [
  { code: "investigation.request_revisit", name: "Request a revisit", description: "Ask for a correction visit.", default_allowed: true, override: null, effective_allowed: true },
  { code: "route.view_own_history", name: "View own route history", description: "View earlier routes.", default_allowed: true, override: null, effective_allowed: true },
  { code: "investigation.view_own_history", name: "View own history", description: "Completed investigations, earlier report versions, and activity.", default_allowed: false, override: null, effective_allowed: false },
];
const mandatoryWorkflows = [{ name: "Visit reporting", description: "Reports remain required." }];

async function mockCollector(page: Page, role: "supervisor" | "agent" | "admin", longReference = false) {
  const cases = longReference
    ? sampleCases.map((item, index) => index === 0 ? { ...item, reference_number: "INV-9008E8C4D22D46C09933377C0568BD04", address_display: "Blk 8 Lot 90 Phase 11, Sampaguita, San Jose, Rodriguez, Rizal Region IV-A" } : item)
    : sampleCases;
  await page.route(/^https?:\/\/[^/]+\/(users|investigations|locations|activity-logs|planning|reports|agent-permissions)(\/|$)/, async (route) => {
    if (route.request().resourceType() === "document") return route.continue();
    const url = new URL(route.request().url());
    const path = url.pathname;
    const person = role === "agent" ? sampleAgent : role === "admin" ? sampleAdmin : sampleUser;
    let body: unknown = [];
    if (path === "/users/refresh" || path === "/users/login") body = { access_token: `eyJhbGciOiJub25lIn0.${Buffer.from(JSON.stringify({ sub: String(person.id), sid: "visual-fixture" })).toString("base64url")}.fixture` };
    else if (path === "/users/me") body = person;
    else if (path === "/users/me/agent-permissions") body = { permissions: { "investigation.request_revisit": true, "route.view_own_history": true, "investigation.view_own_history": true } };
    else if (path === "/users/agents") body = [sampleAgent];
    else if (path === "/users/") body = [sampleAdmin, sampleUser, sampleAgent];
    else if (path === "/investigations/") {
      const accessible = role === "agent" ? cases.filter((item) => item.assigned_agent_id === sampleAgent.id) : cases;
      const status = url.searchParams.get("status");
      const priority = url.searchParams.get("priority");
      const query = url.searchParams.get("q")?.toLowerCase().trim();
      const items = accessible.filter((item) =>
        (!status || item.status === status) &&
        (!priority || item.priority === priority) &&
        (!query || `${item.reference_number} ${item.subject_name} ${item.address_display}`.toLowerCase().includes(query)),
      );
      body = { items, total: items.length, page: 1, page_size: 25, facets: {
        status: { pending: accessible.filter((item) => item.status === "pending").length, assigned: accessible.filter((item) => item.status === "assigned").length, in_progress: accessible.filter((item) => item.status === "in_progress").length, under_review: accessible.filter((item) => item.status === "under_review").length, returned_for_correction: 0, completed: accessible.filter((item) => item.status === "completed").length, cancelled: 0 },
        priority: { normal: accessible.filter((item) => item.priority === "normal").length, high: accessible.filter((item) => item.priority === "high").length, urgent: accessible.filter((item) => item.priority === "urgent").length },
        assigned: accessible.filter((item) => item.assigned_agent_id !== null).length, unassigned: accessible.filter((item) => item.assigned_agent_id === null).length, location_unconfirmed: 0,
      } };
    }
    else if (path === "/investigations/trash") body = [cases[0]];
    else if (/^\/investigations\/\d+$/.test(path)) body = cases.find((item) => item.id === Number(path.split("/").pop())) ?? cases[0];
    else if (/^\/investigations\/\d+\/report$/.test(path)) body = null;
    else if (/^\/investigations\/\d+\/location$/.test(path)) body = null;
    else if (path === "/reports/review-queue") {
      const items = [{ report_id: 1, investigation_id: 1, reference_number: cases[0].reference_number, subject_name: cases[0].subject_name, assigned_agent_name: sampleAgent.name, author_name: sampleAgent.name, version: 2, priority: "urgent", status: "submitted", submitted_at: "2026-11-04T01:00:00Z", updated_at: "2026-11-04T01:00:00Z" }]
        .filter((item) => !url.searchParams.get("status") || item.status === url.searchParams.get("status"));
      body = { items, total: items.length, page: 1, page_size: 25 };
    }
    else if (path === "/investigations/awaiting-no-contact-review") body = { items: [], total: 0, page: 1, page_size: 25 };
    else if (path === "/locations/regions") body = [{ code: "1300000000", name: "National Capital Region" }];
    else if (path.endsWith("/provinces")) body = [];
    else if (path.endsWith("/cities-municipalities")) body = [{ code: "1374040000", name: "Quezon City" }];
    else if (path.endsWith("/barangays")) body = [{ code: "1374040010", name: "Diliman" }];
    else if (path === "/planning/agent-shifts") body = [{ agent: sampleAgent, shift: null, assigned_workload_count: 2, availability_day: { status: "not_configured", is_available: false } }];
    else if (path === "/planning/my-route") body = {
      work_date: url.searchParams.get("work_date") || "2026-11-08", route_revision: 1,
      current_actionable_investigation_id: 2, reason: null, shift: null,
      route: { agent_id: 2, agent_name: sampleAgent.name, geometry_status: "ready", geometry_error_code: null, geometry: { type: "LineString", coordinates: [[121.05, 14.65], [121.06, 14.66], [121.07, 14.67]] }, geometry_digest: "a".repeat(64), total_distance_metres: 7200, total_travel_seconds: 1500, total_service_seconds: 5400, total_planned_waiting_seconds: 0, total_break_seconds: 0, planned_departure_at: "2026-11-08T00:00:00Z", start: { latitude: 14.65, longitude: 121.05, label: "Configured field office" }, end: null },
      stops: cases.slice(1, 3).map((item, index) => ({ investigation_id: item.id, reference_number: item.reference_number, address_display: item.address_display, latitude: item.latitude, longitude: item.longitude, priority: item.priority, status: item.status, sequence: index + 1, sequence_state: index === 0 ? "current" : "upcoming", can_start: index === 0, can_report: false, travel_seconds: 750, travel_metres: 3600, service_duration_seconds: 2700, estimated_arrival_at: `2026-11-08T0${index + 1}:00:00Z`, planned_arrival_at: `2026-11-08T0${index + 1}:00:00Z` })),
    };
    else if (path === "/activity-logs/filter-options") body = {
      actions: ["investigation.updated"],
      object_types: ["investigation"],
      actors: [{ id: sampleUser.id, name: sampleUser.name }],
    };
    else if (path === "/activity-logs/query") body = {
      items: [{ id: 1, created_at: "2026-11-04T01:00:00Z", actor_id: sampleUser.id, actor_name: sampleUser.name, action: "investigation.updated", object_type: "investigation", object_id: 1, record_label: "INV-2026-0001 · Fictional Subject 1 (Investigation ID: 1)", summary: "Investigation updated: Priority", detail_fields: [{ key: "fields", label: "Fields", value: "Priority", redacted: false }] }],
      total: 1,
      page: Number(url.searchParams.get("page") ?? "1"),
      page_size: Number(url.searchParams.get("page_size") ?? "25"),
    };
    else if (path === "/activity-logs/") body = [{ id: 1, created_at: "2026-11-04T01:00:00Z", actor_name: sampleUser.name, action: "investigation.updated", object_type: "investigation", object_id: 1, details: { fields: ["priority"] } }];
    else if (path === "/agent-permissions/catalog") body = { features: permissionFeatures, mandatory_workflows: mandatoryWorkflows };
    else if (path.startsWith("/users/2/agent-permissions")) body = path.endsWith("/history") ? { items: [], total: 0, limit: 50, offset: 0 } : { agent: sampleAgent, features: permissionFeatures, mandatory_workflows: mandatoryWorkflows };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

test("capture Collector recovery surfaces", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const role = (process.env.VISUAL_ROLE === "agent" ? "agent" : process.env.VISUAL_ROLE === "admin" ? "admin" : "supervisor") as "agent" | "supervisor" | "admin";
  await mockCollector(page, role);
  const phase = process.env.VISUAL_PHASE || "after";
  const routes = role === "agent"
    ? ["dashboard", "investigations", "my-route", "investigations/2"]
    : role === "admin"
      ? ["dashboard", "users", "access-control", "activity-logs", "investigations/trash"]
      : ["dashboard", "investigations", "investigations/new", "investigations/1", "field-agents", "reports", "route-planning"];
  for (const width of [1440, 1366, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of routes) {
      if (page.url() === "about:blank") await page.goto("/dashboard");
      else await page.evaluate((target) => { window.history.pushState({}, "", target); window.dispatchEvent(new PopStateEvent("popstate")); }, `/${path}`);
      await expect(page.locator("#main-content")).toBeVisible();
      await page.waitForTimeout(500);
      expect(errors, `Browser errors on /${path}`).toEqual([]);
      if (path !== "route-planning") {
        const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        expect(hasHorizontalOverflow, `Horizontal overflow on /${path} at ${width}px`).toBe(false);
      }
      await page.screenshot({ path: `/tmp/collector-${phase}-${role}-${path.replaceAll("/", "-")}-${width}.png`, fullPage: true });
    }
  }
});

test("capture Collector sign-in", async ({ page }) => {
  await page.route("**/users/refresh", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Unauthenticated" }) }));
  for (const width of [1440, 1366, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/sign-in");
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    await page.screenshot({ path: `/tmp/collector-after-sign-in-${width}.png`, fullPage: true });
  }
});

test("table filters, long identifiers, row actions, and sidebar toggle stay usable", async ({ page }) => {
  await mockCollector(page, "supervisor", true);
  await page.goto("/dashboard");
  await page.evaluate(() => {
    window.history.pushState({}, "", "/investigations");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page.getByRole("heading", { name: "Investigation register" })).toBeVisible();

  const priority = page.getByRole("combobox", { name: "Priority" });
  await priority.click();
  await expect(page.getByRole("option", { name: "Urgent" })).toBeVisible();
  await page.getByRole("option", { name: "Urgent" }).click();
  await expect(page).toHaveURL(/priority=urgent/);
  await expect(page.locator(".investigation-table tbody tr")).toHaveCount(1);

  const status = page.getByRole("combobox", { name: "Status" });
  await status.click();
  await page.getByRole("option", { name: "Pending" }).click();
  await expect(page).toHaveURL(/status=pending/);

  const reference = "INV-9008E8C4D22D46C09933377C0568BD04";
  const referenceLabel = page.locator(`.investigation-table tbody tr span[title="${reference}"]`);
  await expect(referenceLabel).toBeVisible();
  const truncation = await referenceLabel.evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }));
  expect(truncation.scroll).toBeGreaterThan(truncation.client);
  await page.screenshot({ path: "/tmp/collector-table-long-reference-1440.png", fullPage: true });

  const rowMenu = page.getByRole("button", { name: `Actions for ${reference}` });
  await rowMenu.click();
  await expect(page.getByRole("menuitem", { name: "View details" })).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.locator(".investigation-table tbody tr")).toHaveCount(5);
  await page.getByRole("button", { name: "Collapse navigation" }).click();
  await expect(page.getByRole("button", { name: "Expand navigation" })).toBeVisible();
  await page.screenshot({ path: "/tmp/collector-sidebar-collapsed-1440.png", fullPage: true });
  await page.getByRole("button", { name: "Expand navigation" }).click();
  await priority.click();
  await expect(page.getByRole("option", { name: "Urgent" })).toBeVisible();
  await page.screenshot({ path: "/tmp/collector-table-filter-open-1440.png", fullPage: true });
});

test("Activity Logs filters apply together and cancel draft changes", async ({ page }) => {
  await mockCollector(page, "admin");
  await page.goto("/dashboard");
  await page.evaluate(() => {
    window.history.pushState({}, "", "/activity-logs");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();

  const filters = page.getByRole("button", { name: "Filters", exact: true });
  await filters.click();
  await expect(page.getByRole("heading", { name: "Filter activity logs" })).toBeVisible();
  await page.getByLabel("Search logs").fill("priority");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page).not.toHaveURL(/q=priority/);

  await filters.click();
  await page.getByLabel("Search logs").fill("priority");
  await page.getByLabel("From date").fill("2026-11-10");
  await page.getByLabel("To date").fill("2026-11-09");
  await expect(page.getByRole("button", { name: "Apply filters" })).toBeDisabled();
  await page.getByLabel("To date").fill("2026-11-11");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/q=priority/);
  await expect(page.getByRole("button", { name: /Filters 3/ })).toBeVisible();
});
