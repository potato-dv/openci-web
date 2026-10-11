type TopbarProps = {
  title: string;
  isLoading: boolean;
  onRefresh: () => void;
};

export function Topbar({ title, isLoading, onRefresh }: TopbarProps) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">OPENCI OPERATIONS</p>
        <h1>{title}</h1>
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
      </div>
    </header>
  );
}
