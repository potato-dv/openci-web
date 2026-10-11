import type { UserRole } from "../../types/api";

type RoleBadgeProps = {
  role: UserRole;
};

export function RoleBadge({ role }: RoleBadgeProps) {
  return <span className="role-badge">{role}</span>;
}
