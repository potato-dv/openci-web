import { Breadcrumbs } from "./Breadcrumbs";
import { AccountDropdown } from "./AccountDropdown";
import type { User } from "../../types/api";

type TopbarProps = {
  title: string;
  isLoading: boolean;
  onRefresh: () => void;
  user: User;
  onLogout: () => void;
  breadcrumbs?: {
    parentLabel: string;
    currentLabel: string;
    onParentClick: () => void;
  };
};

export function Topbar({ title, isLoading, onRefresh, user, onLogout, breadcrumbs }: TopbarProps) {
  return (
    <header className="topbar">
      <div>
        {breadcrumbs ? (
          <Breadcrumbs {...breadcrumbs} />
        ) : title ? (
          <h1>{title}</h1>
        ) : null}
      </div>

      <div className="topbar-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={onRefresh}
          disabled={isLoading}
        >
          {isLoading ? "Refreshing..." : "Refresh Data"}
        </button>
        <AccountDropdown user={user} onLogout={onLogout} />
      </div>
    </header>
  );
}
