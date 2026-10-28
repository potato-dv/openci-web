import type { NewUser, User } from "@/types/api";
import { requestJson } from "@/services/http";

export function getUsers(token: string) {
  return requestJson<User[]>("/users/", { token });
}

export function createUser(token: string, user: NewUser) {
  return requestJson<User>("/users/", {
    method: "POST",
    token,
    body: JSON.stringify(user),
  });
}

export function updateUserActivation(
  token: string,
  userId: number,
  isActive: boolean,
) {
  return requestJson<User>(`/users/${userId}/activation`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ is_active: isActive }),
  });
}

export function updateUserRole(
  token: string,
  userId: number,
  role: User["role"],
) {
  return requestJson<User>(`/users/${userId}/role`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ role }),
  });
}
