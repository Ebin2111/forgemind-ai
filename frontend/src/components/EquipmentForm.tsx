"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { errorMessage, titleCase } from "@/lib/format";
import type { Equipment, EquipmentStatus } from "@/types";

const STATUSES: EquipmentStatus[] = ["operational", "maintenance", "fault", "retired"]; // the values the backend accepts

/** Add a machine (no `existing`) or edit one. The tag is fixed once the machine exists. */
export default function EquipmentForm({
  existing, statusOnly = false, onDone, onClose,
}: {
  existing?: Equipment;
  /** Technicians may change only the status; the other fields are shown but locked. */
  statusOnly?: boolean;
  onDone: (e: Equipment) => void;
  onClose: () => void;
}) {
  const [tag, setTag] = useState(existing?.tag ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const [type, setType] = useState(existing?.type ?? "");
  const [location, setLocation] = useState(existing?.location ?? "");
  const [manufacturer, setManufacturer] = useState(existing?.manufacturer ?? "");
  const [status, setStatus] = useState<EquipmentStatus>(existing?.status ?? "operational");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    const fields = { name: name.trim(), type: type.trim(), location: location.trim(), manufacturer: manufacturer.trim(), status };
    try {
      onDone(
        existing
          ? await api.updateEquipment(existing.id, statusOnly ? { status } : fields) // technicians send only the status
          : await api.createEquipment({ tag: tag.trim(), ...fields }),
      );
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <div className="form-grid two">
        <label className="field"><span>Tag</span>
          <input type="text" value={tag} onChange={(e) => setTag(e.target.value)} required maxLength={50} disabled={!!existing} placeholder="e.g. CMP-201" />
        </label>
        <label className="field"><span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value as EquipmentStatus)}>
            {STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
          </select>
        </label>
      </div>
      <label className="field"><span>Name</span>
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={200} disabled={statusOnly} placeholder="e.g. Rotary screw air compressor" />
      </label>
      <div className="form-grid two">
        <label className="field"><span>Type <em className="hint">(optional)</em></span>
          <input type="text" value={type} onChange={(e) => setType(e.target.value)} maxLength={100} disabled={statusOnly} placeholder="Compressor, pump, CNC…" />
        </label>
        <label className="field"><span>Manufacturer <em className="hint">(optional)</em></span>
          <input type="text" value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} maxLength={100} disabled={statusOnly} />
        </label>
      </div>
      <label className="field"><span>Location <em className="hint">(optional)</em></span>
        <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} maxLength={200} disabled={statusOnly} placeholder="Utility room, line 2…" />
      </label>
      {statusOnly && <p className="muted">Only an administrator can change the other details. You can update the status.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="btn-row">
        <button type="submit" disabled={busy || name.trim().length < 2 || (!existing && !tag.trim())}>{busy ? "Saving…" : existing ? "Save changes" : "Add equipment"}</button>
        <button type="button" className="ghost" onClick={onClose} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}