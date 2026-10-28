import type { LoginResponse, User } from "@/types/api";
import { requestJson } from "@/services/http";

export function login(email: string, password: string) {
  return requestJson<LoginResponse>("/users/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getProfile(token: string) {
  return requestJson<User>("/users/me", { token });
}
