import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { useRef, useState } from "react";
import type { Investigation } from "@/types/api";
import {
  permanentlyDeleteInvestigation,
  restoreInvestigation,
} from "@/features/investigations/api";
import { InvestigationSubjectCell } from "@/components/data/InvestigationSubjectCell";
import { formatUserName } from "@/utils/userName";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Modal } from "@/components/ui/Modal";
import { SectionToolbar } from "@/components/layout/SectionToolbar";
import { RowActions } from "@/components/ui/RowActions";
import { EmptyState, InlineAlert, Skeleton } from "@/components/ui/Primitives";

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

  function trashActions(item: Investigation) {
    return (
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
    );
  }

  return (
    <section className="content-card">
      <SectionToolbar
        title="Deleted investigations"
        description="Restore investigations or permanently delete them. Permanent deletion also removes their reports, reviews, and assignment history."
        actions={<span className="count-badge">{items.length} in Trash</span>}
      />
      {error && <InlineAlert onRetry={onRetry}>{error}</InlineAlert>}
      {actionError && !confirmItem && <InlineAlert>{actionError}</InlineAlert>}
      {successMessage && <p className="success-message" role="status" aria-live="polite">{successMessage}</p>}
      {loading ? (
        <Skeleton rows={4} />
      ) : items.length === 0 ? (
        <EmptyState title="Trash is empty">Deleted investigations will appear here until they are restored or permanently removed.</EmptyState>
      ) : (
        <>
        <div className="table-wrap desktop-data">
          <Table className="trash-table min-w-[760px] table-fixed">
            <colgroup>
              <col className="w-[24%]" />
              <col className="w-[32%]" />
              <col className="w-[18%]" />
              <col className="w-[18%]" />
              <col className="w-[8%]" />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Subject</TableHead>
                <TableHead scope="col">Address</TableHead>
                <TableHead scope="col">Last workflow status</TableHead>
                <TableHead scope="col">Assigned agent</TableHead>
                <TableHead scope="col" className="trash-actions-heading text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="trash-actions-cell">
                    <InvestigationSubjectCell
                      subjectName={item.subject_name}
                      referenceNumber={item.reference_number}
                    />
                  </TableCell>
                  <TableCell className="max-w-0 truncate" title={item.address_display || item.legacy_address || undefined}>{item.address_display || item.legacy_address || "—"}</TableCell>
                  <TableCell><StatusBadge status={item.status} reopenOn={item.reopen_on} /></TableCell>
                  <TableCell>{item.assigned_agent_name ? formatUserName(item.assigned_agent_name) : "Unassigned"}</TableCell>
                  <TableCell className="text-right">{trashActions(item)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <ul className="workspace-mobile-list" aria-label="Deleted investigations">
          {items.map((item) => (
            <li key={item.id}>
              <div className="mobile-row-heading">
                <InvestigationSubjectCell subjectName={item.subject_name} referenceNumber={item.reference_number} />
                {trashActions(item)}
              </div>
              <span className="mobile-row-meta">{item.address_display || item.legacy_address || "Address unavailable"}</span>
              <dl className="mobile-row-facts">
                <div><dt>Status</dt><dd><StatusBadge status={item.status} reopenOn={item.reopen_on} /></dd></div>
                <div><dt>Agent</dt><dd>{item.assigned_agent_name ? formatUserName(item.assigned_agent_name) : "Unassigned"}</dd></div>
              </dl>
            </li>
          ))}
        </ul>
        </>
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
