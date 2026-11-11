"use client";

import { useEffect, useState } from "react";

import Drawer from "@/components/Drawer";
import EmptyState from "@/components/EmptyState";
import { api } from "@/lib/api";
import { errorMessage, formatDate, titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useFetch } from "@/lib/useFetch";
import type { Role, User } from "@/types";

const ROLES: Role[] = ["technician", "admin"];
const MIN_PASSWORD = 8;
const EMAIL = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;
const USERS_ICON = "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8z";

/** Add a person (no `existing`) or edit one: name, role, active switch and an optional new password. */
function UserForm({ existing, isMe, onDone, onClose }: { existing?: User; isMe: boolean; onDone: (message: string) => void; onClose: () => void }) {
  const [email, setEmail] = useState(existing?.email ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const [role, setRole] = useState<Role>(existing?.role ?? "technician");
  const [active, setActive] = useState(existing?.is_active ?? true);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const passwordOk = existing ? password === "" || password.length >= MIN_PASSWORD : password.length >= MIN_PASSWORD;
  const valid = (existing || EMAIL.test(email.trim())) && passwordOk;

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (existing) {
        await api.updateUser(existing.id, { name: name.trim(), role, is_active: active, ...(password ? { password } : {}) });
        onDone(`${existing.email} saved.`);
      } else {
        const created = await api.createUser({ email: email.trim(), name: name.trim(), role, password });
        onDone(`${created.email} can now sign in.`);
      }
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={submit} autoComplete="off">
      <label className="field"><span>Email</span>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} disabled={!!existing} placeholder="name@company.com" />
      </label>
      <label className="field"><span>Name <em className="hint">(optional)</em></span>
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} placeholder="e.g. Priya Raman" />
      </label>
      <label className="field"><span>Role</span>
        <select value={role} onChange={(e) => setRole(e.target.value as Role)} disabled={isMe}>
          {ROLES.map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}
        </select>
        <em className="hint">
          {role === "admin"
            ? "Administrators can upload and delete documents, add or delete equipment, import files and manage users."
            : "Technicians can read everything, ask questions, create and update work orders and change a machine's status."}
        </em>
      </label>
      {existing && (
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} disabled={isMe} />
          <span>Account is active (switch off to block sign-in)</span>
        </label>
      )}
      <label className="field"><span>{existing ? "New password" : "Password"} {existing && <em className="hint">(leave empty to keep the current one)</em>}</span>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password"
               required={!existing} minLength={MIN_PASSWORD} maxLength={200} placeholder={`At least ${MIN_PASSWORD} characters`} />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="btn-row">
        <button type="submit" disabled={busy || !valid}>{busy ? "Saving…" : existing ? "Save changes" : "Create user"}</button>
        <button type="button" className="ghost" onClick={onClose} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

export default function UsersPage() {
  const { session, isAdmin } = useSession();
  const users = useFetch(() => (isAdmin ? api.users() : Promise.resolve([] as User[])), [isAdmin]);
  const [form, setForm] = useState<"add" | User | null>(null);
  const [toast, setToast] = useState<{ text: string; bad?: boolean } | null>(null);
  useEffect(() => { document.title = "Users | ForgeMind AI"; }, []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4500);
    return () => clearTimeout(t);
  }, [toast]);

  if (!isAdmin) {
    return (
      <div className="panel"><EmptyState icon={USERS_ICON} title="Administrators only">Ask an administrator if you need an account changed.</EmptyState></div>
    );
  }

  async function remove(u: User) {
    if (!window.confirm(`Delete the account ${u.email}? They will no longer be able to sign in.`)) return;
    try {
      await api.deleteUser(u.id);
      setToast({ text: `${u.email} deleted.` });
      users.reload();
    } catch (err) {
      setToast({ text: errorMessage(err), bad: true });
    }
  }

  const list = users.data ?? [];
  return (
    <div>
      <header className="page-header">
        <div>
          <h1 className="page-title">Users</h1>
          <p className="page-sub">Who can sign in to ForgeMind, and what they are allowed to do.</p>
        </div>
        <div className="btn-row"><button type="button" onClick={() => setForm("add")}>Add user</button></div>
      </header>

      {users.error && <div className="alert" role="alert"><p>{users.error}</p><button type="button" onClick={users.reload}>Try again</button></div>}
      {users.loading && !users.data && <div className="skeleton" style={{ height: 200 }} />}
      {users.data && list.length === 0 && <div className="panel"><EmptyState icon={USERS_ICON} title="No users">Use Add user to create the first account.</EmptyState></div>}

      {list.length > 0 && (
        <div className="panel table-scroll">
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Added</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {list.map((u) => {
                const isMe = u.email === session?.email;
                return (
                  <tr key={u.id}>
                    <td>{u.name || <span className="muted">-</span>}{isMe && <span className="badge" style={{ marginLeft: 8 }}>You</span>}</td>
                    <td>{u.email}</td>
                    <td><span className={`badge${u.role === "admin" ? " ok" : ""}`}>{titleCase(u.role)}</span></td>
                    <td><span className={`badge${u.is_active ? " ok" : " warn"}`}>{u.is_active ? "Active" : "Switched off"}</span></td>
                    <td>{formatDate(u.created_at)}</td>
                    <td>
                      <span className="btn-row">
                        <button type="button" className="ghost small" onClick={() => setForm(u)}>Edit</button>
                        <button type="button" className="danger small" onClick={() => remove(u)} disabled={isMe} title={isMe ? "You cannot delete your own account" : undefined}>Delete</button>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Drawer open={form !== null} onClose={() => setForm(null)} title={form === "add" ? "Add user" : "Edit user"}
              subtitle={form !== null && form !== "add" ? form.email : "They sign in with this email and password."}>
        {form !== null && (
          <UserForm key={form === "add" ? "new" : form.id} existing={form === "add" ? undefined : form}
                    isMe={form !== "add" && form.email === session?.email} onClose={() => setForm(null)}
                    onDone={(text) => { setForm(null); setToast({ text }); users.reload(); }} />
        )}
      </Drawer>

      {toast && <div className={`toast${toast.bad ? " bad" : ""}`} role="status">{toast.text}</div>}
    </div>
  );
}