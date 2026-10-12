import { useState } from "react";
import type { FormEvent } from "react";
import { deleteInvestigation, updateInvestigation } from "../services/api";
import type { Investigation, User } from "../types/api";
import { AssignmentPanel } from "../components/investigations/AssignmentPanel";
import { PhilippineAddressFields } from "../components/investigations/PhilippineAddressFields";
import { ReportEditor } from "../components/investigations/ReportEditor";
import { ReviewPanel } from "../components/investigations/ReviewPanel";
import { StatusBadge } from "../components/ui/StatusBadge";
import { PriorityBadge } from "../components/ui/PriorityBadge";
import { Modal } from "../components/ui/Modal";

type InvestigationDetailsPageProps = {
  token: string;
  user: User;
  investigation: Investigation;
  onBack: () => void;
  onChanged: () => void;
  onDeleted: () => void;
};

export function InvestigationDetailsPage({
  token,
  user,
  investigation,
  onBack,
  onChanged,
  onDeleted,
}: InvestigationDetailsPageProps) {
  const canManage = user.role === "admin" || user.role === "supervisor";
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [form, setForm] = useState({
    subject_name: investigation.subject_name,
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
      subject_name: investigation.subject_name,
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
    setSaving(true);
    setError("");
    try {
      await updateInvestigation(token, investigation.id, {
        subject_name: form.subject_name,
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
    setDeleteError("");
    setArchiving(true);
    try {
      await deleteInvestigation(token, investigation.id);
      onDeleted();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Could not archive investigation.");
      setConfirmArchive(false);
    } finally {
      setArchiving(false);
    }
  }

  return (
    <div className="details-layout">
      <button type="button" className="secondary-button toolbar-button back-button" onClick={onBack}>Back to investigations</button>
      <section className="details-summary">
        <div className="section-heading">
          <div>
            <h2>{investigation.reference_number}</h2>
            <p>{investigation.subject_name}</p>
          </div>
          <StatusBadge status={investigation.status} />
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
            <dd>{investigation.assigned_agent_name ?? "Unassigned"}</dd>
          </div>
        </dl>
      </section>

      {deleteError && <p className="error" role="alert">{deleteError}</p>}
      {canManage && <div className="details-actions">
        <button className="secondary-button toolbar-button" type="button" onClick={openEditForm}>Edit investigation</button>
        {user.role === "admin" && <button className="danger-button" type="button" onClick={() => { setDeleteError(""); setConfirmArchive(true); }}>Archive investigation</button>}
      </div>}
      {user.role === "admin" && <Modal open={confirmArchive} title="Archive investigation" onClose={() => !archiving && setConfirmArchive(false)}>
        <div className="confirm-dialog-copy">
          <p>Archive investigation <strong>{investigation.reference_number}</strong>?</p>
          <p>Its reports, reviews, and assignment history will be retained.</p>
          {deleteError && <p className="error" role="alert">{deleteError}</p>}
          <div className="modal-form-actions">
            <button type="button" className="secondary-button toolbar-button" onClick={() => setConfirmArchive(false)} disabled={archiving}>Cancel</button>
            <button type="button" className="danger-button toolbar-button" onClick={() => void handleDelete()} disabled={archiving}>{archiving ? "Archiving…" : "Archive investigation"}</button>
          </div>
        </div>
      </Modal>}
      {canManage && <Modal open={editing} title={`Edit ${investigation.reference_number}`} size="wide" onClose={() => setEditing(false)}>
        <form className="create-form modal-form" onSubmit={handleSave}>
          <label>Subject name<input required maxLength={255} value={form.subject_name} onChange={(event) => setForm({ ...form, subject_name: event.target.value })} /></label>
          <PhilippineAddressFields token={token} value={form} onChange={setForm} />
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
