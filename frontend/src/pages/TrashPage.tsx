import { useRef, useState } from "react";
import type { Investigation } from "../types/api";
import { permanentlyDeleteInvestigation, restoreInvestigation } from "../services/api";
import { InvestigationSubjectCell } from "../components/data/InvestigationSubjectCell";
import { formatUserName } from "../utils/userName";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Modal } from "../components/ui/Modal";
import { SectionToolbar } from "../components/layout/SectionToolbar";
import { RowActions } from "../components/ui/RowActions";

type TrashPageProps = {
  token: string;
  isAdmin: boolean;
  items: Investigation[];
  loading: boolean;
  error: string;
  onRetry: () => void;
  onRestored: (item: Investigation) => void;
  onPermanentlyDeleted: (item: Investigation) => void;
};

export function TrashPage({
  token,
  isAdmin,
  items,
  loading,
  error,
  onRetry,
  onRestored,
  onPermanentlyDeleted,
}: TrashPageProps) {
  const [restoreId, setRestoreId] = useState<number | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [confirmItem, setConfirmItem] = useState<Investigation | null>(null);
  const [actionError, setActionError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const actionInFlight = useRef(false);

  async function handleRestore(item: Investigation) {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setActionError("");
    setSuccessMessage("");
    setRestoreId(item.id);
    try {
      const restored = await restoreInvestigation(token, item.id);
      onRestored(restored);
      setSuccessMessage(`${item.reference_number} was restored to investigations.`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not restore investigation.");
    } finally {
      actionInFlight.current = false;
      setRestoreId(null);
    }
  }

  async function handlePermanentDelete() {
    if (!confirmItem || actionInFlight.current) return;
    const item = confirmItem;
    actionInFlight.current = true;
    setActionError("");
    setSuccessMessage("");
    setDeleteId(item.id);
    try {
      await permanentlyDeleteInvestigation(token, item.id);
      onPermanentlyDeleted(item);
      setConfirmItem(null);
      setSuccessMessage(`${item.reference_number} was permanently deleted.`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not permanently delete investigation.");
    } finally {
      actionInFlight.current = false;
      setDeleteId(null);
    }
  }

  const busy = restoreId !== null || deleteId !== null;

  return (
    <section className="content-card">
      <SectionToolbar
        title="Trash"
        description="Restore investigations or permanently delete them. Permanent deletion also removes their reports, reviews, and assignment history."
        actions={<span className="count-badge">{items.length} in Trash</span>}
      />
      {error && <p className="error" role="alert">{error} <button className="inline-link-button" type="button" onClick={onRetry}>Retry</button></p>}
      {actionError && !confirmItem && <p className="error" role="alert">{actionError}</p>}
      {successMessage && <p className="success-message" role="status" aria-live="polite">{successMessage}</p>}
      {loading ? (
        <p className="muted" role="status">Loading Trash…</p>
      ) : items.length === 0 ? (
        <p className="empty-state">Trash is empty.</p>
      ) : (
        <div className="table-wrap">
          <table className="trash-table">
            <thead>
              <tr>
                <th scope="col">Subject</th>
                <th scope="col">Address</th>
                <th scope="col">Last workflow status</th>
                <th scope="col">Assigned agent</th>
                <th scope="col" className="trash-actions-heading">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="trash-actions-cell">
                    <InvestigationSubjectCell
                      subjectName={item.subject_name}
                      referenceNumber={item.reference_number}
                    />
                  </td>
                  <td>{item.address_display || item.legacy_address || "—"}</td>
                  <td><StatusBadge status={item.status} /></td>
                  <td>{item.assigned_agent_name ? formatUserName(item.assigned_agent_name) : "Unassigned"}</td>
                  <td>
                    <RowActions label={item.reference_number}>
                      <button
                        type="button"
                        role="menuitem"
                        disabled={busy}
                        onClick={() => void handleRestore(item)}
                      >
                        {restoreId === item.id ? "Restoring…" : "Restore"}
                      </button>
                      {isAdmin && (
                        <button
                          type="button"
                          role="menuitem"
                          className="danger-menu-item"
                          disabled={busy}
                          onClick={() => { setActionError(""); setSuccessMessage(""); setConfirmItem(item); }}
                        >
                          Permanently delete
                        </button>
                      )}
                    </RowActions>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isAdmin && (
        <Modal
          open={confirmItem !== null}
          title="Permanently delete investigation"
          onClose={() => !busy && setConfirmItem(null)}
        >
          <div className="confirm-dialog-copy">
            <p>Permanently delete <strong>{confirmItem?.reference_number}</strong>?</p>
            <p>This cannot normally be undone. Its reports, reviews, and assignment history will also be deleted.</p>
            {actionError && <p className="error" role="alert">{actionError}</p>}
            <div className="modal-form-actions">
              <button
                type="button"
                className="secondary-button toolbar-button"
                onClick={() => setConfirmItem(null)}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button toolbar-button"
                onClick={() => void handlePermanentDelete()}
                disabled={busy}
              >
                {deleteId === confirmItem?.id ? "Deleting…" : "Permanently delete"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </section>
  );
}
