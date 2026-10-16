import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { deleteInvestigation, updateInvestigation } from "../services/api";
import type { Investigation, User } from "../types/api";
import { AssignmentPanel } from "../components/investigations/AssignmentPanel";
import { PhilippineAddressFields } from "../components/investigations/PhilippineAddressFields";
import { ReportEditor } from "../components/investigations/ReportEditor";
import { ReviewPanel } from "../components/investigations/ReviewPanel";
import { formatUserName } from "../utils/userName";
import { StatusBadge } from "../components/ui/StatusBadge";
import { PriorityBadge } from "../components/ui/PriorityBadge";
import { Modal } from "../components/ui/Modal";

type InvestigationDetailsPageProps = {
  token: string;
  user: User;
  investigation: Investigation;
  onChanged: () => void;
  onDeleted: (item: Investigation) => void;
};

export function InvestigationDetailsPage({
  token,
  user,
  investigation,
  onChanged,
  onDeleted,
}: InvestigationDetailsPageProps) {
  const canManage = user.role === "admin" || user.role === "supervisor";
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [softDeleting, setSoftDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteInFlight = useRef(false);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [form, setForm] = useState({
    first_name: investigation.first_name ?? "",
    middle_name: investigation.middle_name ?? "",
    last_name: investigation.last_name ?? "",
    house_number: investigation.house_number ?? "",
    unit_floor_building_name: investigation.unit_floor_building_name ?? "",
    street: investigation.street ?? "",
    subdivision_village_purok: investigation.subdivision_village_purok ?? "",
    region_code: investigation.region_code ?? "",
    province_code: investigation.province_code ?? "",
    city_municipality_code: investigation.city_municipality_code ?? "",
    barangay_code: investigation.barangay_code ?? "",
    postal_code: investigation.postal_code ?? "",
    priority: investigation.priority,
  });

  function openEditForm() {
    setForm({
      first_name: investigation.first_name ?? "",
      middle_name: investigation.middle_name ?? "",
      last_name: investigation.last_name ?? "",
      house_number: investigation.house_number ?? "",
      unit_floor_building_name: investigation.unit_floor_building_name ?? "",
      street: investigation.street ?? "",
      subdivision_village_purok: investigation.subdivision_village_purok ?? "",
      region_code: investigation.region_code ?? "",
      province_code: investigation.province_code ?? "",
      city_municipality_code: investigation.city_municipality_code ?? "",
      barangay_code: investigation.barangay_code ?? "",
      postal_code: investigation.postal_code ?? "",
      priority: investigation.priority,
    });
    setError("");
    setEditing(true);
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      await updateInvestigation(token, investigation.id, {
        first_name: form.first_name,
        middle_name: form.middle_name.trim() || null,
        last_name: form.last_name,
        house_number: form.house_number,
        unit_floor_building_name: form.unit_floor_building_name || null,
        street: form.street,
        subdivision_village_purok: form.subdivision_village_purok || null,
        region_code: form.region_code,
        province_code: form.province_code || null,
        city_municipality_code: form.city_municipality_code,
        barangay_code: form.barangay_code,
        postal_code: form.postal_code || null,
        priority: form.priority,
      });
      setEditing(false);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update investigation.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (deleteInFlight.current) return;
    deleteInFlight.current = true;
    setDeleteError("");
    setSoftDeleting(true);
    try {
      await deleteInvestigation(token, investigation.id);
      onDeleted(investigation);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Could not move investigation to Trash.");
    } finally {
      deleteInFlight.current = false;
      setSoftDeleting(false);
    }
  }

  return (
    <div className="details-layout">
      <section className="details-summary">
        <div className="details-page-heading">
          <div className="details-page-identity">
            <h1>{formatUserName(investigation.subject_name)}</h1>
            <p className="details-reference">{investigation.reference_number}</p>
          </div>
          <div className="details-page-controls">
            {canManage && (
              <div className="details-actions">
                <button className="secondary-button toolbar-button" type="button" onClick={openEditForm}>Edit investigation</button>
                <button className="danger-button toolbar-button" type="button" onClick={() => { setDeleteError(""); setConfirmDelete(true); }}>Move to Trash</button>
              </div>
            )}
          </div>
        </div>
        <dl className="details-grid">
          <div>
            <dt>Address</dt>
            <dd>{investigation.address_display}</dd>
          </div>
          <div>
            <dt>Priority</dt>
            <dd><PriorityBadge priority={investigation.priority} /></dd>
          </div>
          <div>
            <dt>Assigned agent</dt>
            <dd>{investigation.assigned_agent_name ? formatUserName(investigation.assigned_agent_name) : "Unassigned"}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd><StatusBadge status={investigation.status} /></dd>
          </div>
        </dl>
      </section>

      {canManage && <Modal open={confirmDelete} title="Move investigation to Trash" onClose={() => !softDeleting && setConfirmDelete(false)}>
        <div className="confirm-dialog-copy">
          <p>Move <strong>{investigation.reference_number}</strong> to Trash?</p>
          <p>The investigation and its history will be retained. An administrator can permanently delete it from Trash.</p>
          {deleteError && <p className="error" role="alert">{deleteError}</p>}
          <div className="modal-form-actions">
            <button type="button" className="secondary-button toolbar-button" onClick={() => setConfirmDelete(false)} disabled={softDeleting}>Cancel</button>
            <button type="button" className="danger-button toolbar-button" onClick={() => void handleDelete()} disabled={softDeleting}>{softDeleting ? "Moving to Trash…" : "Move to Trash"}</button>
          </div>
        </div>
      </Modal>}
      {canManage && <Modal open={editing} title={`Edit ${investigation.reference_number}`} size="wide" onClose={() => setEditing(false)}>
        <form className="create-form modal-form" onSubmit={handleSave}>
          {investigation.first_name === null || investigation.last_name === null ? (
            <p className="form-hint" role="status">This legacy name has not been split into name parts. Confirm the correct parts before saving: “{formatUserName(investigation.subject_name)}”.</p>
          ) : null}
          <div className="subject-name-grid">
            <label htmlFor="edit_subject_first_name">First name<input id="edit_subject_first_name" autoComplete="given-name" required maxLength={255} value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} /></label>
            <label htmlFor="edit_subject_middle_name">Middle name <span className="optional-label">Optional</span><input id="edit_subject_middle_name" autoComplete="additional-name" maxLength={255} value={form.middle_name} onChange={(event) => setForm({ ...form, middle_name: event.target.value })} /></label>
            <label htmlFor="edit_subject_last_name">Last name<input id="edit_subject_last_name" autoComplete="family-name" required maxLength={255} value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} /></label>
          </div>
          <PhilippineAddressFields token={token} value={form} onChange={(next) => setForm((current) => ({ ...current, ...next, middle_name: next.middle_name ?? "" }))} />
          <label>Priority<select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value as typeof form.priority })}><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="modal-form-actions">
            <button className="secondary-button toolbar-button" type="button" onClick={() => setEditing(false)} disabled={saving}>Cancel</button>
            <button className="primary-button toolbar-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save changes"}</button>
          </div>
        </form>
      </Modal>}

      {(user.role === "supervisor" || user.role === "admin") && (
        <AssignmentPanel
          token={token}
          investigation={investigation}
          onChanged={onChanged}
        />
      )}

      {user.role === "agent" && (
        <ReportEditor
          token={token}
          investigation={investigation}
          onChanged={onChanged}
        />
      )}

      {(user.role === "supervisor" || user.role === "admin") && (
        <ReviewPanel
          token={token}
          investigation={investigation}
          onChanged={onChanged}
        />
      )}
    </div>
  );
}
