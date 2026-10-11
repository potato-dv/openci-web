type NoticeProps = {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
};

export function Notice({ message, actionLabel, onAction }: NoticeProps) {
  return (
    <div className="notice error-notice" role="alert">
      <span>{message}</span>
      {actionLabel && onAction && (
        <button className="text-button" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
