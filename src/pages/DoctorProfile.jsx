import { motion } from "framer-motion";
import { ArrowLeft, BadgeCheck, Building2, CheckCircle2, LockKeyhole, Mail, Phone, Save, Stethoscope, UserRound } from "lucide-react";
import { createElement, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const display = (value) => value || "Not provided";

function ReadOnlyDetail({ icon, label, value }) {
  return <div className="rounded-xl border border-border bg-slate-50/80 p-4 dark:border-slate-600 dark:bg-slate-700/40">
    <div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">{createElement(icon, { size: 17 })}</span><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">{label}</p><LockKeyhole size={13} className="text-slate-400" aria-label="Read only" /></div><p className="mt-1 truncate font-semibold">{display(value)}</p></div></div>
  </div>;
}

export default function DoctorProfile() {
  const { doctor, updateProfile } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: doctor?.email || "", phone: doctor?.phone || "" });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const changed = form.email.trim().toLowerCase() !== (doctor?.email || "").toLowerCase() || form.phone !== (doctor?.phone || "");

  const submit = async (event) => {
    event.preventDefault(); setError(""); setMessage("");
    if (form.phone && !/^\d{7,15}$/.test(form.phone)) { setError("Phone number must contain 7 to 15 digits."); return; }
    setSaving(true);
    try {
      await updateProfile({ email: form.email.trim(), phone: form.phone });
      setMessage("Contact details updated successfully.");
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  };

  return <section className="mx-auto max-w-5xl pb-8">
    <button type="button" onClick={() => navigate('/dashboard')} className="mb-5 inline-flex items-center gap-2 text-sm font-semibold text-primary transition hover:-translate-x-1"><ArrowLeft size={16} />Back to dashboard</button>
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_18px_50px_rgba(15,37,64,0.12)] dark:border-slate-700 dark:bg-slate-800">
      <div className="relative overflow-hidden bg-gradient-to-br from-[#102A46] via-[#185477] to-[#0E887E] px-6 py-8 text-white sm:px-9">
        <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-white/10" /><div className="absolute -bottom-20 right-24 h-44 w-44 rounded-full bg-cyan-200/10" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center"><span className="grid h-20 w-20 shrink-0 place-items-center rounded-2xl border border-white/25 bg-white/15 shadow-lg backdrop-blur"><UserRound size={36} /></span><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-100">Doctor profile</p><h1 className="mt-1 text-3xl font-bold tracking-tight">{doctor?.name}</h1><div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-cyan-50"><span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1"><BadgeCheck size={15} />Verified clinician</span><span>{display(doctor?.specialty)}</span></div></div></div>
      </div>

      <form onSubmit={submit} className="grid gap-7 p-6 sm:p-9 lg:grid-cols-[1.1fr_0.9fr]">
        <div><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent"><Mail size={19} /></span><div><h2 className="text-lg font-bold">Contact information</h2><p className="text-sm text-slate-500 dark:text-slate-300">These are the only profile details you can edit.</p></div></div>
          <div className="mt-5 space-y-4"><label className="block text-sm font-semibold">Professional email<div className="relative mt-1.5"><Mail size={16} className="absolute left-3 top-3 text-slate-400" /><input required type="email" autoComplete="email" className="input pl-10" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></div></label><label className="block text-sm font-semibold">Phone number<div className="relative mt-1.5"><Phone size={16} className="absolute left-3 top-3 text-slate-400" /><input type="tel" inputMode="numeric" autoComplete="tel" maxLength="15" className="input pl-10" placeholder="Add phone number" value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value.replace(/\D/g, "") })} /></div></label></div>
          {error && <p role="alert" className="mt-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm font-semibold text-danger">{error}</p>}
          {message && <p role="status" className="mt-4 flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 p-3 text-sm font-semibold text-success"><CheckCircle2 size={17} />{message}</p>}
          <button type="submit" disabled={!changed || saving} className="btn-primary mt-5"><Save size={16} />{saving ? "Saving…" : "Save contact details"}</button>
        </div>

        <div className="rounded-2xl border border-primary/20 bg-primary/5 p-5"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><LockKeyhole size={18} /></span><div><h2 className="text-lg font-bold">Professional details</h2><p className="text-sm text-slate-500 dark:text-slate-300">Protected account information</p></div></div><div className="mt-5 grid gap-3"><ReadOnlyDetail icon={UserRound} label="Full name" value={doctor?.name} /><ReadOnlyDetail icon={Stethoscope} label="Specialty" value={doctor?.specialty} /><ReadOnlyDetail icon={Building2} label="Practice setting" value={doctor?.practiceSetting} /><ReadOnlyDetail icon={BadgeCheck} label="Gender" value={doctor?.gender} /></div><p className="mt-4 flex gap-2 text-xs leading-relaxed text-slate-500 dark:text-slate-300"><LockKeyhole size={14} className="mt-0.5 shrink-0" />Contact an administrator if protected professional information needs correction.</p></div>
      </form>
    </motion.div>
  </section>;
}
