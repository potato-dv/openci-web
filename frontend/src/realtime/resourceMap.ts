export type RealtimeNotification = {
  type: "event";
  event_id: string;
  name: string;
  entity_type: string;
  entity_id: number | string;
  investigation_id: number | null;
  timestamp: string;
  affected_agent_id?: number;
};

export type ResourceInvalidator = () => void;

export const EVENT_TO_RESOURCE_KEYS: Record<string, readonly string[]> = {
  "investigation.created": ["investigations.list", "dashboard.investigations", "route.planning", "route.own"],
  "investigation.updated": ["investigations.list", "dashboard.investigations", "route.planning", "route.own"],
  "investigation.location_updated": ["investigations.list", "dashboard.investigations", "route.planning", "route.own"],
  "investigation.revisit_updated": ["investigations.list", "dashboard.investigations", "route.planning", "route.own"],
  "investigation.assigned": ["investigations.list", "dashboard.investigations", "route.planning", "route.own"],
  "investigation.unassigned": ["investigations.list", "dashboard.investigations", "route.planning", "route.own"],
  "investigation.status_changed": ["investigations.list", "dashboard.investigations", "dashboard.reports", "route.planning", "route.own"],
  "investigation.priority_changed": ["investigations.list", "dashboard.investigations", "route.planning", "route.own"],
  "investigation.deleted": ["investigations.list", "investigations.trash", "dashboard.investigations", "route.planning", "route.own"],
  "investigation.restored": ["investigations.list", "investigations.trash", "dashboard.investigations", "route.planning", "route.own"],
  "report.submitted": ["reports.queue", "dashboard.reports", "investigations.list", "dashboard.investigations", "route.own"],
  "report.updated": ["reports.queue", "investigations.list"],
  "report.reviewed": ["reports.queue", "dashboard.reports", "investigations.list", "dashboard.investigations", "route.own"],
  "report.returned_for_correction": ["reports.queue", "dashboard.reports", "investigations.list", "dashboard.investigations", "route.own"],
  "report.completed": ["reports.queue", "dashboard.reports", "investigations.list", "dashboard.investigations", "route.own"],
  "route.published": ["route.planning", "route.readiness", "route.own", "dashboard.route", "investigations.list"],
  "route.replanned": ["route.planning", "route.readiness", "route.own", "dashboard.route", "investigations.list"],
  "route.cancelled": ["route.planning", "route.readiness", "route.own", "dashboard.route", "investigations.list"],
  "route.updated": ["route.planning", "route.own", "dashboard.route"],
  "route.agent_updated": ["route.planning", "route.own", "dashboard.route", "investigations.list"],
  "activity.created": ["activity.logs"],
  "user.created": ["users.list"],
  "user.role_changed": ["users.list", "agent.permissions"],
  "user.permissions_changed": [],
  "user.activated": ["users.list", "agent.permissions"],
  "user.deactivated": ["users.list", "agent.permissions"],
  "schedule.updated": ["schedules.list", "route.planning", "route.own"],
  "shift.updated": ["schedules.list", "route.planning", "route.own", "dashboard.route"],
  "shift.activated": ["schedules.list", "route.planning", "route.own", "dashboard.route"],
  "shift.expired": ["schedules.list", "route.planning", "route.own", "dashboard.route"],
};

export function resourceKeysForEvent(event: RealtimeNotification): string[] {
  const keys = new Set(EVENT_TO_RESOURCE_KEYS[event.name] ?? []);
  if (
    (event.name.startsWith("schedule.") || event.name.startsWith("shift.")) &&
    Number.isInteger(event.affected_agent_id) &&
    (event.affected_agent_id ?? 0) > 0
  ) {
    keys.add(`schedules.${event.affected_agent_id}`);
  }
  if (
    ["user.role_changed", "user.activated", "user.deactivated"].includes(event.name) &&
    Number.isInteger(event.entity_id) &&
    Number(event.entity_id) > 0
  ) {
    keys.add(`schedules.${event.entity_id}`);
  }
  if (event.name === "user.permissions_changed" && event.entity_id != null) {
    keys.add(`agent.permissions:${event.entity_id}`);
  }
  if (event.investigation_id !== null) {
    if (event.name.startsWith("report.")) {
      keys.add(`investigation.report:${event.investigation_id}`);
    }
    if (event.name !== "investigation.revisit_updated") {
      keys.add(`investigation:${event.investigation_id}`);
    }
    keys.add(`investigation.activity:${event.investigation_id}`);
    if (event.name === "investigation.location_updated") {
      keys.add(`investigation-location:${event.investigation_id}`);
    }
    if (event.name === "investigation.revisit_updated") {
      keys.add(`investigation.revisit:${event.investigation_id}`);
    }
  }
  return [...keys];
}

export function subscriptionScopeForResource(resourceKey: string): string | null {
  if (resourceKey.startsWith("investigation:")) return resourceKey;
  if (resourceKey.startsWith("investigation-location:")) {
    return `investigation:${resourceKey.slice("investigation-location:".length)}`;
  }
  if (resourceKey.startsWith("investigation.revisit:")) {
    return `investigation:${resourceKey.slice("investigation.revisit:".length)}`;
  }
  if (resourceKey.startsWith("investigation.report:")) {
    return `investigation:${resourceKey.slice("investigation.report:".length)}`;
  }
  if (resourceKey.startsWith("investigation.activity:")) {
    return `investigation:${resourceKey.slice("investigation.activity:".length)}`;
  }
  if (resourceKey === "route.own") return "route.own";
  if (resourceKey === "reports.queue") return "reports.queue";
  if (resourceKey.startsWith("route.") || resourceKey === "dashboard.route") return "route.planning";
  if (resourceKey === "activity.logs") return "activity.logs";
  if (resourceKey.startsWith("agent.permissions:")) return "users";
  if (resourceKey === "users.list" || resourceKey === "agent.permissions") return resourceKey === "users.list" ? "users" : "me";
  if (resourceKey === "investigations.trash") return "investigations";
  if (resourceKey.startsWith("schedules.")) return "schedules";
  if (resourceKey === "dashboard.investigations" || resourceKey === "dashboard.reports" || resourceKey === "investigations.list") return "investigations";
  return "dashboard";
}
