import type { MapInvestigation, MapRoute, MapSelection } from "./mapTypes";

export function routesForSelection(
  routes: MapRoute[],
  selection: MapSelection,
  investigations: MapInvestigation[],
) {
  if (selection === null) return routes;
  const agentId =
    selection.type === "agent"
      ? selection.id
      : (investigations.find((item) => item.id === selection.id)?.agent_id ??
        null);
  return agentId == null
    ? []
    : routes.filter((route) => route.agent_id === agentId);
}
