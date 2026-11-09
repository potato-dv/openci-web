import { describe, expect, it } from "vitest";
import {
  resourceKeysForEvent,
  subscriptionScopeForResource,
  type RealtimeNotification,
} from "./resourceMap";

function event(name: string, investigationId: number | null = null): RealtimeNotification {
  return {
    type: "event",
    event_id: "event-1",
    name,
    entity_type: "investigation_report",
    entity_id: 12,
    investigation_id: investigationId,
    timestamp: "2026-11-09T08:00:00Z",
  };
}

describe("central real-time resource mapping", () => {
  it("invalidates the report queue, dashboard, and open case resources on submission", () => {
    expect(resourceKeysForEvent(event("report.submitted", 7))).toEqual([
      "reports.queue",
      "dashboard.reports",
      "investigations.list",
      "dashboard.investigations",
      "route.own",
      "investigation.report:7",
      "investigation:7",
      "investigation.activity:7",
    ]);
  });

  it("uses the agent route scope and route REST resources for route publication", () => {
    const keys = resourceKeysForEvent(event("route.published"));
    expect(keys).toContain("route.own");
    expect(keys).toContain("route.planning");
    expect(keys).toContain("dashboard.route");
    expect(subscriptionScopeForResource("route.own")).toBe("route.own");
    expect(subscriptionScopeForResource("route.readiness")).toBe("route.planning");
  });

  it("subscribes to an investigation only through its validated resource scope", () => {
    expect(subscriptionScopeForResource("investigation.report:7")).toBe("investigation:7");
    expect(subscriptionScopeForResource("investigation-location:7")).toBe("investigation:7");
    expect(subscriptionScopeForResource("investigation.activity:7")).toBe("investigation:7");
  });

  it("does not invalidate unrelated resources for an activity event", () => {
    expect(resourceKeysForEvent(event("activity.created"))).toEqual(["activity.logs"]);
  });

  it("targets an admin permission refresh only to the changed agent resource", () => {
    const changed = event("user.permissions_changed");
    changed.entity_id = 41;
    expect(resourceKeysForEvent(changed)).toEqual(["agent.permissions:41"]);
    expect(subscriptionScopeForResource("agent.permissions:41")).toBe("users");
  });

  it("targets the affected agent's open schedule and shift resources", () => {
    expect(resourceKeysForEvent({
      ...event("schedule.updated"),
      entity_type: "agent_schedule",
      affected_agent_id: 17,
    })).toContain("schedules.17");
    expect(resourceKeysForEvent({
      ...event("shift.expired"),
      entity_type: "agent_shift",
      affected_agent_id: 23,
    })).toContain("schedules.23");
    expect(resourceKeysForEvent(event("user.deactivated", null))).toContain("schedules.12");
  });
});
