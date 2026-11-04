import { test, expect, type Locator, type Page } from "@playwright/test";
const agent = {
  id: 2,
  name: "Alex Reyes",
  email: "alex@example.test",
  role: "agent",
  is_active: true,
};
const supervisor = {
  id: 1,
  name: "Jamie Cruz",
  email: "jamie@example.test",
  role: "supervisor",
  is_active: true,
};
const start = {
  latitude: 14.65,
  longitude: 121.05,
  label: "Configured field office, Quezon City",
};
const shift = {
  id: 1,
  agent_id: 2,
  work_date: "2026-11-04",
  region_code: "1300000000",
  is_available: true,
  shift_starts_at: "2026-11-04T00:00:00Z",
  shift_ends_at: "2026-11-04T09:00:00Z",
  start_latitude: start.latitude,
  start_longitude: start.longitude,
  end_latitude: null,
  end_longitude: null,
  max_visits: 8,
  max_open_cases: 20,
  current_planning_run_id: null,
  start_location_label: start.label,
};
const cases = Array.from({ length: 4 }, (_, index) => ({
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
  priority: index === 0 ? "urgent" : "normal",
  status: "pending",
  assigned_agent_id: null,
  assigned_agent_name: null,
  location_confirmed: true,
  created_at: "2026-10-21T01:00:00Z",
  service_duration_seconds: 2700,
  latitude: 14.65 + index * 0.01,
  longitude: 121.06 + index * 0.01,
}));
const geometry = {
  type: "LineString",
  coordinates: [
    [121.05, 14.65],
    [121.055, 14.652],
    [121.06, 14.65],
    [121.06, 14.66],
    [121.07, 14.66],
    [121.07, 14.67],
    [121.08, 14.67],
    [121.08, 14.68],
    [121.09, 14.68],
  ],
};
const route = {
  agent_id: 2,
  agent_name: agent.name,
  geometry_status: "ready",
  geometry_error_code: null,
  geometry,
  geometry_digest: "b".repeat(64),
  total_distance_metres: 14500,
  total_travel_seconds: 1800,
  start,
  end: null,
};
const routeStops = cases.map((item, index) => ({
  service_duration_seconds: item.service_duration_seconds,
  investigation_id: item.id,
  reference_number: item.reference_number,
  address_display: item.address_display,
  latitude: item.latitude,
  longitude: item.longitude,
  priority: item.priority,
  status: item.status,
  prior_agent_id: null,
  agent_id: 2,
  agent_name: agent.name,
  outcome: "assigned",
  reason: null,
  sequence: index + 1,
  estimated_arrival_at: `2026-11-04T0${index + 1}:00:00Z`,
  travel_seconds: 450,
  travel_metres: 3500,
}));
async function fixture(
  page: Page,
  options: {
    role?: string;
    missingGeometry?: boolean;
    locationFailure?: boolean;
    secondAgent?: boolean;
    reportQueue?: boolean;
    needsConfirmation?: boolean;
  } = {},
) {
  const counts = { creates: 0 };
  const secondAgent = { ...agent, id: 3, name: "Other Field Agent" };
  const unlocatedCase = {
    id: 99,
    reference_number: "INV-2026-0005",
    status: "pending",
    region_code: "1300000000",
  };
  await page.addInitScript(() =>
    sessionStorage.setItem("access_token", "fixture-only"),
  );
  await page.route("**/tile.openstreetmap.org/**", (request) =>
    request.fulfill({
      contentType: "image/png",
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jA0cAAAAASUVORK5CYII=",
        "base64",
      ),
    }),
  );
  await page.route("http://localhost:8000/**", async (request) => {
    const url = new URL(request.request().url());
    const path = url.pathname;
    const method = request.request().method();
    let body: unknown;
    let status = 200;
    if (path === "/users/me")
      body = options.role === "agent" ? agent : supervisor;
    else if (path === "/users/agents") body = [agent];
    else if (path === "/locations/regions")
      body = [{ code: "1300000000", name: "National Capital Region" }];
    else if (path.endsWith("/provinces")) body = [];
    else if (path.endsWith("/cities-municipalities"))
      body = [{ code: "1374040000", name: "Quezon City" }];
    else if (path.endsWith("/barangays"))
      body = [{ code: "1374040010", name: "Diliman" }];
    else if (path === "/locations/geocode-suggestions")
      body = [
        {
          label: "Example Road, Diliman, Quezon City",
          category: "road",
          latitude: 14.65,
          longitude: 121.05,
          provider_ref: "way/123",
        },
      ];
    else if (path === "/investigations/" && method === "POST") {
      counts.creates += 1;
      body = { ...cases[0], id: 20, location_confirmed: false };
    } else if (path === "/investigations/")
      body = {
        items: url.searchParams.get("q") === "none" ? [] : cases,
        total: url.searchParams.get("q") === "none" ? 0 : 4,
        page: Number(url.searchParams.get("page") || 1),
        page_size: Number(url.searchParams.get("page_size") || 25),
        facets: {
          status: {
            pending: 4,
            assigned: 0,
            in_progress: 0,
            under_review: 0,
            returned_for_correction: 0,
            completed: 0,
          },
          priority: { normal: 3, high: 0, urgent: 1 },
          assigned: 0,
          unassigned: 4,
          location_unconfirmed: 0,
        },
      };
    else if (/^\/investigations\/\d+$/.test(path))
      body = { ...cases[0], id: Number(path.split("/").pop()) };
    else if (path.endsWith("/location") && method === "PUT") {
      status = options.locationFailure ? 503 : 200;
      body = options.locationFailure
        ? { detail: "geocoder_unavailable" }
        : cases[0];
    } else if (path.endsWith("/location")) body = null;
    else if (/\/(assignments|reviews|reports)$/.test(path)) body = [];
    else if (path.endsWith("/report")) body = null;
    else if (path === "/reports/review-queue")
      body = {
        items: options.reportQueue
          ? [
              {
                report_id: 1,
                investigation_id: 1,
                reference_number: cases[0].reference_number,
                subject_name: cases[0].subject_name,
                assigned_agent_name: agent.name,
                author_name: agent.name,
                version: 2,
                priority: "urgent",
                status: "submitted",
                submitted_at: "2026-11-04T01:00:00Z",
                updated_at: "2026-11-04T01:00:00Z",
              },
            ]
          : [],
        total: options.reportQueue ? 1 : 0,
        page: 1,
        page_size: 25,
      };
    else if (path === "/planning/agent-shifts")
      body = [
        { agent, shift, approved_workload_count: 0 },
        ...(options.secondAgent
          ? [
              {
                agent: secondAgent,
                shift: { ...shift, id: 2, agent_id: 3 },
                approved_workload_count: 0,
              },
            ]
          : []),
      ];
    else if (path === "/planning/readiness") {
      body = {
        work_date: url.searchParams.get("work_date"),
        region_code: url.searchParams.get("region_code"),
        resolution: Number(url.searchParams.get("resolution") || 8),
        active_agent_count: 1,
        unavailable_agent_count: 0,
        eligible_cases: [],
        available_agents: [],
        excluded_cases: [],
        density: [],
      };
    } else if (path === "/planning/dashboard") {
      body = {
        work_date: url.searchParams.get("work_date"),
        region_code: url.searchParams.get("region_code"),
        total_investigations:
          cases.length + (options.needsConfirmation ? 1 : 0),
        automatically_assigned: cases.length,
        unassigned_investigations: options.needsConfirmation ? 1 : 0,
        active_agents: 1,
        available_agents: 1,
        optimizing_routes: 0,
        published_routes: 1,
        failed_planning_jobs: 0,
        investigation_states: [
          ...cases.map((item) => ({
            investigation_id: item.id,
            planning_status: "assigned",
            reason: null,
            planning_run_id: 7,
            assignment_source: "automatic",
          })),
          ...(options.needsConfirmation
            ? [
                {
                  investigation_id: unlocatedCase.id,
                  planning_status: "unassigned",
                  reason: "location_unconfirmed",
                  planning_run_id: null,
                  assignment_source: null,
                },
              ]
            : []),
        ],
      };
    } else if (path === "/planning/map-data") {
      const regionCode = url.searchParams.get("region_code");
      const mapAgents = [
        { user: agent, agentShift: shift },
        ...(options.secondAgent
          ? [
              {
                user: secondAgent,
                agentShift: { ...shift, id: 2, agent_id: 3 },
              },
            ]
          : []),
      ].filter(
        ({ agentShift }) =>
          !regionCode || agentShift.region_code === regionCode,
      );
      body = {
        work_date: shift.work_date,
        region_code: regionCode,
        investigations: cases
          .filter((item) => !regionCode || item.region_code === regionCode)
          .map((item) => ({
            id: item.id,
            reference_number: item.reference_number,
            address_display: item.address_display,
            latitude: item.latitude,
            longitude: item.longitude,
            priority: item.priority,
            status: item.status,
            region_code: item.region_code,
            assigned_agent_id: 2,
            assigned_agent_name: agent.name,
          })),
        agents: mapAgents.map(({ user, agentShift }) => ({
          id: user.id,
          name: user.name,
          is_active: user.is_active,
          region_code: agentShift.region_code,
          is_available: agentShift.is_available,
          shift_starts_at: agentShift.shift_starts_at,
          shift_ends_at: agentShift.shift_ends_at,
          start,
        })),
        unlocated_investigations: options.needsConfirmation
          ? [unlocatedCase]
          : [],
        unlocated_agents: [],
      };
    } else if (path === "/planning/route-overview") {
      const regionCode = url.searchParams.get("region_code");
      const currentRoute = options.missingGeometry
        ? {
            ...route,
            geometry_status: "failed",
            geometry_error_code: "route_geometry_incomplete",
            geometry: null,
          }
        : { ...route, shift };
      body = {
        work_date: shift.work_date,
        region_code: regionCode,
        agents: [
          {
            id: agent.id,
            name: agent.name,
            is_active: agent.is_active,
            region_code: shift.region_code,
            shift,
            route_status: options.missingGeometry ? "failed" : "published",
            refresh_errors: options.missingGeometry
              ? ["route_geometry_incomplete"]
              : [],
            refresh_investigation_id: 1,
            run_id: 7,
            route: currentRoute,
            stops: options.missingGeometry ? [] : routeStops,
          },
          ...(options.secondAgent
            ? [
                {
                  id: secondAgent.id,
                  name: secondAgent.name,
                  is_active: secondAgent.is_active,
                  region_code: shift.region_code,
                  shift: { ...shift, id: 2, agent_id: secondAgent.id },
                  route_status: "none",
                  refresh_errors: [],
                  refresh_investigation_id: null,
                  run_id: null,
                  route: null,
                  stops: [],
                },
              ]
            : []),
        ],
      };
    } else if (/\/planning\/(my-route|agents\/\d+\/route)$/.test(path))
      body = {
        work_date: shift.work_date,
        reason: null,
        shift,
        route: { ...route, shift },
        stops: routeStops.map(
          ({
            investigation_id,
            reference_number,
            address_display,
            sequence,
            estimated_arrival_at,
            travel_seconds,
            travel_metres,
            latitude,
            longitude,
            priority,
            status,
            service_duration_seconds,
          }) => ({
            investigation_id,
            reference_number,
            address_display,
            sequence,
            estimated_arrival_at,
            travel_seconds,
            travel_metres,
            latitude,
            longitude,
            priority,
            status,
            service_duration_seconds,
          }),
        ),
      };
    else if (/\/planning\/agents\/\d+\/shifts\//.test(path)) body = shift;
    else {
      status = 500;
      body = { detail: `Unhandled test fixture: ${path}` };
    }
    await request.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  return counts;
}
test("assignment-generated routes fit supported viewports without manual plan actions", async ({
  page,
}) => {
  await fixture(page, { needsConfirmation: true });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/route-planning?date=2026-11-04&region=1300000000");
  await expect(
    page.getByRole("heading", { name: "Route Planning" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Stop sequence" }).first(),
  ).toBeVisible();
  await expect(
    page
      .locator(".planning-route-summary")
      .first()
      .getByText("4 stops", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".route-planning-stats")).toContainText(
    "Total investigations",
  );
  await expect(page.locator(".route-planning-stats")).toContainText(
    "Automatically assigned",
  );
  await expect(page.locator(".route-planning-stats")).toContainText(
    "Unassigned",
  );
  await expect(page.locator(".route-planning-stats")).toContainText(
    "Agents available",
  );
  await expect(page.locator(".route-planning-stats")).toContainText(
    "Published routes",
  );
  const wideLayout = await page.evaluate(() => {
    const canvas = document.querySelector(".route-planning-page")!;
    const header = document.querySelector(".route-planning-header")!;
    const stats = document.querySelector(".route-planning-stats")!;
    const map = document.querySelector(".planning-map-region")!;
    const left = document.querySelector(".planning-left")!;
    const right = document.querySelector(".planning-right")!;
    const search = document.querySelector(
      ".route-planning-header .map-search-control",
    )!;
    const refresh = document.querySelector(".route-refresh-button")!;
    const routeHeading = document.querySelector(
      ".planning-right .route-detail-heading > div",
    )!;
    const routeAgentSummary = document.querySelector(
      ".planning-right .planning-route-agent",
    )!;
    const mapFitControls = document.querySelector(".map-fit-controls")!;
    const viewSwitch = document.querySelector(".planning-view-switch")!;
    const rosterSearch = document.querySelector(".route-roster-search")!;
    const rosterIcon = rosterSearch.querySelector("svg")!;
    const rosterInput = rosterSearch.querySelector("input")!;
    const leftCollapse = document.querySelector(
      ".planning-left > .icon-button",
    )!;
    const rightCollapse = document.querySelector(
      ".planning-right > .icon-button",
    )!;
    const rosterDescription = document.querySelector(
      ".planning-left .route-roster-heading > span",
    )!;
    const routeDescription = document.querySelector(
      ".planning-right .route-detail-heading > div > span",
    )!;
    const textRight = (element: Element) => {
      const range = document.createRange();
      range.selectNodeContents(element);
      return Math.max(
        ...Array.from(range.getClientRects(), (rect) => rect.right),
      );
    };
    const bounds = (element: Element) => {
      const rect = element.getBoundingClientRect();
      return {
        top: rect.top,
        bottom: rect.bottom,
        left: rect.left,
        right: rect.right,
      };
    };
    return {
      headerDisplay: getComputedStyle(header).display,
      header: bounds(header),
      canvasWidth: canvas.getBoundingClientRect().width,
      headerWidth: header.getBoundingClientRect().width,
      statsDisplay: getComputedStyle(stats).display,
      stats: bounds(stats),
      canvasHeight: canvas.getBoundingClientRect().height,
      mapHeight: map.getBoundingClientRect().height,
      left: bounds(left),
      right: bounds(right),
      search: bounds(search),
      refresh: bounds(refresh),
      routeHeading: bounds(routeHeading),
      routeAgentSummary: bounds(routeAgentSummary),
      mapLegendHidden: !document.querySelector(".map-legend"),
      mapFitControls: bounds(mapFitControls),
      viewSwitchDisplay: getComputedStyle(viewSwitch).display,
      leftCollapse: bounds(leftCollapse),
      rightCollapse: bounds(rightCollapse),
      rosterDescriptionRight: textRight(rosterDescription),
      routeDescriptionRight: textRight(routeDescription),
      rosterSearch: {
        display: getComputedStyle(rosterSearch).display,
        height: bounds(rosterSearch).bottom - bounds(rosterSearch).top,
        icon: bounds(rosterIcon),
        input: bounds(rosterInput),
      },
    };
  });
  expect(wideLayout.headerDisplay).toBe("flex");
  expect(wideLayout.header.bottom).toBeLessThan(wideLayout.stats.top);
  expect(wideLayout.headerWidth).toBeLessThanOrEqual(wideLayout.canvasWidth);
  expect(wideLayout.statsDisplay).toBe("grid");
  expect(wideLayout.refresh.right).toBeLessThan(wideLayout.search.left);
  expect(
    Math.abs(wideLayout.refresh.bottom - wideLayout.search.bottom),
  ).toBeLessThan(2);
  expect(wideLayout.left.top).toBeGreaterThan(wideLayout.stats.bottom);
  expect(wideLayout.viewSwitchDisplay).toBe("none");
  expect(
    Math.abs(wideLayout.routeHeading.left - wideLayout.routeAgentSummary.left),
  ).toBeLessThan(1);
  expect(wideLayout.mapLegendHidden).toBe(true);
  expect(wideLayout.rosterDescriptionRight).toBeLessThan(
    wideLayout.leftCollapse.left - 8,
  );
  expect(wideLayout.routeDescriptionRight).toBeLessThan(
    wideLayout.rightCollapse.left - 8,
  );
  expect(wideLayout.rosterSearch.display).toBe("flex");
  expect(wideLayout.rosterSearch.height).toBeLessThan(48);
  expect(wideLayout.rosterSearch.input.left).toBeGreaterThan(
    wideLayout.rosterSearch.icon.right,
  );
  expect(
    Math.abs(
      (wideLayout.rosterSearch.input.top +
        wideLayout.rosterSearch.input.bottom) /
        2 -
        (wideLayout.rosterSearch.icon.top +
          wideLayout.rosterSearch.icon.bottom) /
          2,
    ),
  ).toBeLessThan(4);
  expect(wideLayout.mapHeight).toBeGreaterThan(wideLayout.canvasHeight - 1);
  await expect(page.locator(".planning-left")).toBeVisible();
  await expect(page.locator(".planning-right")).toBeVisible();
  await page
    .getByRole("button", { name: "Collapse agent and investigation list" })
    .click();
  await expect(
    page.getByRole("button", { name: "Expand agent and investigation list" }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect(
    page.getByRole("button", { name: "Collapse route details" }),
  ).toHaveAttribute("aria-expanded", "true");
  await page
    .getByRole("button", { name: "Expand agent and investigation list" })
    .click();
  await page.getByRole("button", { name: "Collapse route details" }).click();
  await expect(
    page.getByRole("button", { name: "Expand route details" }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect(
    page.getByRole("button", { name: "Collapse agent and investigation list" }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("button", { name: "Expand route details" }).click();
  await page.getByRole("tab", { name: /Needs confirmation/ }).click();
  const confirmationRecord = page.locator(".planning-left .confirmation-link");
  await expect(confirmationRecord).toContainText("INV-2026-0005");
  const confirmationBounds = await confirmationRecord.boundingBox();
  const recordsBounds = await page.locator(".planning-left").boundingBox();
  expect(confirmationBounds).not.toBeNull();
  expect(recordsBounds).not.toBeNull();
  expect(confirmationBounds!.width).toBeLessThanOrEqual(recordsBounds!.width);
  await page.getByRole("tab", { name: /Investigations/ }).click();
  const mapSearch = page.getByLabel("Search addresses or records on the map");
  await expect(mapSearch).toBeVisible();
  await mapSearch.fill("INV-2026-0001");
  await page.locator(".map-search-results").getByRole("button").first().click();
  await expect(
    page.locator(".planning-right .selected-stop-detail"),
  ).toContainText("INV-2026-0001");
  const investigationFactLayout = await page
    .locator(".planning-investigation-facts > div")
    .first()
    .evaluate((row) => ({
      display: getComputedStyle(row).display,
      columns: getComputedStyle(row)
        .gridTemplateColumns.split(" ")
        .filter(Boolean).length,
    }));
  expect(investigationFactLayout).toEqual({ display: "grid", columns: 2 });
  await page.getByRole("button", { name: "Map layers and style" }).click();
  await expect(page.getByRole("group", { name: "Map style" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Generate plan/i }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Approve assignments/i }),
  ).toHaveCount(0);
  for (const width of [1920, 1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    if (width === 1280 || width === 1440) {
      const headerRow = await page.evaluate(() => {
        const breadcrumb = document
          .querySelector(".route-planning-breadcrumb")!
          .getBoundingClientRect();
        const heading = document
          .querySelector(".route-planning-heading")!
          .getBoundingClientRect();
        const toolbar = document
          .querySelector(".route-planning-toolbar-controls")!
          .getBoundingClientRect();
        return {
          breadcrumbHeight: breadcrumb.height,
          headingRight: heading.right,
          toolbarLeft: toolbar.left,
        };
      });
      expect(headerRow.breadcrumbHeight).toBeLessThan(20);
      expect(headerRow.toolbarLeft).toBeGreaterThanOrEqual(
        headerRow.headingRight + 8,
      );
    }
    if (width === 768 || width === 1024) {
      const headerStack = await page.evaluate(() => {
        const heading = document
          .querySelector(".route-planning-heading")!
          .getBoundingClientRect();
        const toolbar = document
          .querySelector(".route-planning-toolbar-controls")!
          .getBoundingClientRect();
        return { headingBottom: heading.bottom, toolbarTop: toolbar.top };
      });
      expect(headerStack.toolbarTop).toBeGreaterThanOrEqual(
        headerStack.headingBottom + 8,
      );
    }
    if (width === 1280) {
      await expect(page.locator(".planning-right")).toBeHidden();
      const openRouteDetails = page.getByRole("button", {
        name: "Open route details",
      });
      await expect(openRouteDetails).toBeVisible();
      await openRouteDetails.click();
      await expect(
        page.getByRole("heading", { name: "Route details" }),
      ).toBeVisible();
      await page.keyboard.press("Escape");
    }
    if (width >= 1440) {
      const panelHeights = await page.evaluate(() => ({
        left: document.querySelector(".planning-left")!.getBoundingClientRect()
          .height,
        right: document
          .querySelector(".planning-right")!
          .getBoundingClientRect().height,
      }));
      expect(panelHeights.left).toBeGreaterThan(500);
      expect(panelHeights.right).toBeGreaterThan(500);
    }
    if (width === 1024 || width === 768) {
      await expect(page.locator(".planning-left")).toBeHidden();
      await expect(page.locator(".planning-right")).toBeHidden();
      const openRecordList = page.getByRole("button", {
        name: "Open record list",
      });
      const openRouteDetails = page.getByRole("button", {
        name: "Route details",
        exact: true,
      });
      await expect(openRecordList).toBeVisible();
      await expect(openRouteDetails).toBeVisible();
      await openRecordList.click();
      await expect(
        page.getByRole("heading", { name: "Planning records" }),
      ).toBeVisible();
      await page.keyboard.press("Escape");
      await openRouteDetails.click();
      await expect(
        page.getByRole("heading", { name: "Route details" }),
      ).toBeVisible();
      await page.keyboard.press("Escape");
    }
    if (width === 390) {
      await expect(
        page.getByRole("tab", { name: "Routes", exact: true }),
      ).toBeVisible();
      await page.getByRole("tab", { name: "Routes", exact: true }).click();
      await expect(page.locator(".planning-right")).toBeVisible();
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `/tmp/collector-planning-${width}.png`,
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
});
test("header account menu stays anchored and keyboard-accessible across layouts", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/dashboard");

  async function assertMenuFitsViewport(trigger: Locator) {
    const menu = page.getByRole("menu", { name: "Account actions" });
    await trigger.click();
    await expect(menu).toBeVisible();
    await expect(
      menu.getByRole("group", { name: "Signed-in account" }),
    ).toContainText("Jamie Cruz");
    await expect(
      menu.getByRole("group", { name: "Signed-in account" }),
    ).toContainText("jamie@example.test");
    await expect(
      menu.getByRole("group", { name: "Signed-in account" }),
    ).toContainText("supervisor");
    await expect(menu.getByRole("menuitem", { name: "Log out" })).toBeVisible();
    const bounds = await menu.boundingBox();
    const triggerBounds = await trigger.boundingBox();
    expect(bounds).not.toBeNull();
    expect(triggerBounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.y).toBeGreaterThanOrEqual(0);
    expect(bounds!.width).toBeLessThanOrEqual(224);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(
      page.viewportSize()!.width + 1,
    );
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(
      page.viewportSize()!.height + 1,
    );
    expect(bounds!.y).toBeGreaterThanOrEqual(
      triggerBounds!.y + triggerBounds!.height - 1,
    );
    expect(
      Math.abs(
        bounds!.x + bounds!.width - (triggerBounds!.x + triggerBounds!.width),
      ),
    ).toBeLessThanOrEqual(1);
    await trigger.click();
    await expect(menu).toBeHidden();
  }

  for (const width of [1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 800 });
    const trigger = page
      .locator(".app-topbar")
      .getByRole("button", { name: "Account menu for Jamie Cruz, supervisor" });
    await expect(trigger).toBeVisible();
    if (width === 1440) {
      await expect(
        page.locator(".desktop-navigation").getByRole("button", {
          name: "Account menu for Jamie Cruz, supervisor",
        }),
      ).toHaveCount(0);
    }
    await assertMenuFitsViewport(trigger);

    if (width === 1440) {
      await trigger.focus();
      await page.keyboard.press("ArrowDown");
      const menu = page.getByRole("menu", { name: "Account actions" });
      await expect(menu).toBeVisible();
      await expect(
        menu.getByRole("menuitem", { name: "Log out" }),
      ).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(menu).toBeHidden();
      await expect(trigger).toBeFocused();

      await trigger.click();
      await expect(menu).toBeVisible();
      await page.locator("#main-content").click({ position: { x: 8, y: 8 } });
      await expect(menu).toBeHidden();

      await page.getByRole("button", { name: "Collapse navigation" }).click();
      await assertMenuFitsViewport(trigger);
    }
  }
});
test("automatic route failure explains why it was not published and never draws a fallback line", async ({
  page,
}) => {
  await fixture(page, { missingGeometry: true });
  await page.goto("/route-planning?date=2026-11-04&region=1300000000");
  await expect(
    page.getByText("Route update failed", { exact: false }).first(),
  ).toBeVisible();
  await expect(
    page
      .getByText(
        "A complete road route could not be validated, so it was not published.",
      )
      .first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry route update" }),
  ).toBeVisible();
  expect(await page.locator(".leaflet-overlay-pane path").count()).toBe(0);
});

test("all assigned investigation markers remain visible after selection is cleared", async ({
  page,
}) => {
  await fixture(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/route-planning?date=2026-11-04&region=1300000000");
  await expect(page.getByRole("status").first()).toContainText(
    "1 published · 0 updating · 0 need attention",
  );
  await expect(page.locator(".map-symbol.investigation")).toHaveCount(4);
  await page
    .getByRole("button", { name: /INV-2026-0001/ })
    .first()
    .click();
  await page.getByRole("button", { name: "Clear map selection" }).click();
  await expect(page.locator(".map-symbol.investigation")).toHaveCount(4);
  await expect(
    page.locator(".map-symbol.investigation.not-included"),
  ).toHaveCount(0);
});
test("list filters persist in the URL and keyboard navigation opens menus", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/investigations");
  await page.getByRole("searchbox").fill("none");
  await expect(page.getByText("No matching investigations")).toBeVisible();
  expect(page.url()).toContain("q=none");
  await page.reload();
  await expect(page.getByRole("searchbox")).toHaveValue("none");
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(
    page
      .getByRole("link", { name: "INV-2026-0001 Fictional Subject 1" })
      .first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Actions for INV-2026-0001" }).focus();
  await page.keyboard.press("Enter");
  await page
    .getByRole("menuitem", { name: "View details" })
    .waitFor({ state: "visible" });
  await expect(
    page.getByRole("menuitem", { name: "View details" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Actions for INV-2026-0001" }),
  ).toBeFocused();
});
test("creation validates steps and retains the created record after location failure", async ({
  page,
}) => {
  const counts = await fixture(page, { locationFailure: true });
  await page.goto("/investigations/new");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Subject information" }),
  ).toBeVisible();
  await page.getByLabel("First name", { exact: true }).fill("Fictional");
  await page.getByLabel("Last name", { exact: true }).fill("Subject");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("House/building number", { exact: true }).fill("20");
  await page.getByLabel("Street", { exact: true }).fill("Example Road");
  await page
    .getByRole("combobox", { name: "Region", exact: true })
    .selectOption("1300000000");
  await page
    .getByRole("combobox", { name: "City/municipality", exact: true })
    .selectOption("1374040000");
  await page
    .getByRole("combobox", { name: "Barangay", exact: true })
    .selectOption("1374040010");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Find address", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Example Road, Diliman, Quezon City",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Confirm selected point", exact: true })
    .click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByRole("button", { name: "Create investigation", exact: true })
    .click();
  await expect(page).toHaveURL(/\/investigations\/20$/);
  await expect(
    page.getByRole("button", { name: "Retry location confirmation" }),
  ).toBeVisible();
  expect(counts.creates).toBe(1);
});
test("agent route and role guards remain usable on a phone", async ({
  page,
}) => {
  await fixture(page, { role: "agent" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/my-route?date=2026-11-04");
  await expect(
    page.getByRole("heading", { name: "My Route", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "View investigation" }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(
    page.getByRole("dialog").getByRole("link", { name: "Route Planning" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.goto("/users");
  await expect(page.getByText("403 · Access restricted")).toBeVisible();
});
async function fillInvestigation(page: Page) {
  await page.getByLabel("First name", { exact: true }).fill("Fictional");
  await page.getByLabel("Last name", { exact: true }).fill("Subject");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByLabel("House/building number", { exact: true }).fill("20");
  await page.getByLabel("Street", { exact: true }).fill("Example Road");
  await page
    .getByRole("combobox", { name: "Region", exact: true })
    .selectOption("1300000000");
  await page
    .getByRole("combobox", { name: "City/municipality", exact: true })
    .selectOption("1374040000");
  await page
    .getByRole("combobox", { name: "Barangay", exact: true })
    .selectOption("1374040010");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
}
for (const confirmed of [false, true]) {
  test(`creates an investigation with ${confirmed ? "a confirmed point" : "an unconfirmed location"}`, async ({
    page,
  }) => {
    const counts = await fixture(page);
    await page.goto("/investigations/new");
    await fillInvestigation(page);
    if (confirmed) {
      await page
        .getByRole("button", { name: "Find address", exact: true })
        .click();
      await page
        .getByRole("button", {
          name: "Example Road, Diliman, Quezon City",
          exact: true,
        })
        .click();
      await page
        .getByRole("button", { name: "Confirm selected point", exact: true })
        .click();
      await page.getByRole("button", { name: "Continue", exact: true }).click();
    } else
      await page
        .getByRole("button", { name: "Continue without confirmation" })
        .click();
    await page
      .getByRole("button", { name: "Create investigation", exact: true })
      .click();
    await expect(page).toHaveURL(/\/investigations\/20$/);
    expect(counts.creates).toBe(1);
    await expect(
      page.getByRole("button", { name: "Retry location confirmation" }),
    ).toHaveCount(0);
  });
}
test("field agent accounts and shift availability remain distinct", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/field-agents?date=2026-11-04");
  const row = page.getByRole("row").filter({ hasText: agent.name });
  await expect(row.getByText("Active", { exact: true })).toBeVisible();
  await expect(row.getByText("Available", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "View agent" }).click();
  await expect(
    page.getByRole("dialog").getByRole("heading", { name: agent.name }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Assigned work" }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("link", { name: "View investigation" })
      .first(),
  ).toBeVisible();
});

test("editing an earlier wizard step requires validation before returning to review", async ({
  page,
}) => {
  const counts = await fixture(page);
  await page.goto("/investigations/new");
  await fillInvestigation(page);
  await page
    .getByRole("button", { name: "Continue without confirmation" })
    .click();
  await page.locator(".form-stepper button").nth(0).click();
  await page.getByLabel("First name", { exact: true }).fill("   ");
  await expect(page.locator(".form-stepper button").nth(4)).toBeDisabled();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByText("Enter the subject’s first and last name."),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Subject information", exact: true }),
  ).toBeVisible();
  expect(counts.creates).toBe(0);
});

test("route list exposes each agent separately and region filtering is optional", async ({
  page,
}) => {
  await fixture(page, { secondAgent: true });
  await page.goto("/route-planning?date=2026-11-04");
  await page.getByRole("tab", { name: /Agents/ }).click();
  await expect(
    page
      .locator(".route-roster .agent-roster-item", {
        hasText: "Other Field Agent",
      })
      .first(),
  ).toBeVisible();
  await expect(page.getByLabel("Service region (optional)")).toHaveValue("");
  await page.getByLabel("Service region (optional)").selectOption("1300000000");
  await expect(page).toHaveURL(/region=1300000000/);
  await expect(page.locator(".map-symbol.investigation")).toHaveCount(4);
});

test("roster and report queues use accessible compact lists on phones", async ({
  page,
}) => {
  await fixture(page, { reportQueue: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/field-agents?date=2026-11-04");
  const roster = page.getByRole("list", { name: "Field agent roster" });
  await expect(roster).toBeVisible();
  await expect(
    roster.getByText("Account active", { exact: false }),
  ).toBeVisible();
  await expect(roster.getByText("Available", { exact: true })).toBeVisible();
  await roster.getByRole("button", { name: /View agent/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.goto("/reports");
  const reports = page.getByRole("list", { name: "Report queue" });
  await expect(reports).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
  await reports
    .getByRole("link", { name: "Review report", exact: true })
    .click();
  await expect(page).toHaveURL(/\/investigations\/1#report$/);
});
