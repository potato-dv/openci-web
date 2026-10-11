import { useEffect, useState } from "react";

import { getInvestigations, getUsers } from "../services/api";
import type { Investigation, User } from "../types/api";

export function useWorkspaceData(
  user: User | null,
  accessToken: string,
  refreshKey: number,
) {
  const [users, setUsers] = useState<User[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user || !accessToken) {
      return;
    }

    const currentUser = user;
    let cancelled = false;

    async function loadWorkspaceData() {
      setIsLoading(true);
      setError("");

      try {
        const investigationData = await getInvestigations(accessToken);
        const userData =
          currentUser.role === "admin" ? await getUsers(accessToken) : [];

        if (!cancelled) {
          setInvestigations(investigationData);
          setUsers(userData);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load dashboard data.",
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadWorkspaceData();

    return () => {
      cancelled = true;
    };
  }, [accessToken, refreshKey, user]);

  return {
    users,
    investigations,
    isLoading,
    error,
    setUsers,
    setInvestigations,
  };
}
