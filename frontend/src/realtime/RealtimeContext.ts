import { createContext, useContext } from "react";
import type { ResourceInvalidator } from "./resourceMap";

export type RealtimeContextValue = {
  subscribeResources: (keys: readonly string[], invalidator: ResourceInvalidator) => () => void;
  connected: boolean;
};

const inactiveContext: RealtimeContextValue = {
  subscribeResources: () => () => undefined,
  connected: false,
};

export const RealtimeContext = createContext<RealtimeContextValue>(inactiveContext);

export function useRealtimeContext() {
  return useContext(RealtimeContext);
}
