import { createContext, useContext } from "react";
import type { User } from "../types/api";
export const SessionContext = createContext<{
  token: string;
  user: User;
  logout: () => void;
} | null>(null);
export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("An authenticated session is required.");
  return value;
}
