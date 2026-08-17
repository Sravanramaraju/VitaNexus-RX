import { motion } from 'framer-motion'
import { ArrowRight, ShieldCheck, Stethoscope } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Register() {
  const { doctor, register } = useAuth(); const navigate = useNavigate(); const [form, setForm] = useState({ name: '', phone: '', email: '', gender: '', specialty: '', practiceSetting: '', password: '', confirmPassword: '' }); const [error, setError] = useState('')
  if (doctor) return <Navigate to="/dashboard" replace />
  const submit = async (event) => {
    event.preventDefault(); setError('')
    if (form.phone.length < 7 || form.phone.length > 15) { setError('Enter a valid phone number.'); return }
    if (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/\d/.test(form.password) || !/[^A-Za-z0-9]/.test(form.password)) {
      setError('Password must be at least 8 characters and include a letter, number, and special character.'); return
    }
    if (form.password !== form.confirmPassword) { setError('Password and confirm password must match.'); return }
    try {
      await register(form.name, form.email, form.password, { phone: form.phone, gender: form.gender, specialty: form.specialty, practiceSetting: form.practiceSetting })
      navigate('/dashboard')
    } catch (err) { setError(err.message) }
  }
  return <main className="register-page"><div className="register-page__shell">
    <header className="register-page__header"><div className="register-page__brand"><span><Stethoscope size={17} /></span>VitaNexus-RX</div><p>Clinical decision support</p></header>
    <section className="register-page__content"><div className="register-page__intro"><span className="register-page__intro-icon"><ShieldCheck size={23} /></span><p>Welcome to your workspace</p><h1>Start every clinical decision with clarity.</h1><span>Set up your clinician profile and bring your patient workflow into one focused place.</span></div>
      <motion.form initial={{ opacity: 0, x: 22 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, ease: 'easeOut' }} onSubmit={submit} className="register-page__form"><div className="register-page__form-heading"><p>Clinician profile</p><h1>Create your account</h1><span>Tell us a little about your practice.</span></div><div className="register-page__fields">
        <label className="register-page__field">Full name<input required autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value.replace(/\d/g, '') })} onKeyDown={(e) => { if (/\d/.test(e.key)) e.preventDefault() }} className="input mt-1" placeholder="Dr. Priya Sharma" /></label>
        <label className="register-page__field">Phone number<input required type="tel" inputMode="numeric" autoComplete="tel" maxLength="15" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value.replace(/\D/g, '') })} className="input mt-1" placeholder="9876543210" /></label>
        <label className="register-page__field register-page__field--wide">Professional email<input required type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="input mt-1" placeholder="you@hospital.com" /></label>
        <label className="register-page__field">Gender<select required value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })} className="input mt-1"><option value="">Select gender</option><option>Female</option><option>Male</option><option>Non-binary</option><option>Prefer not to say</option></select></label>
        <label className="register-page__field">Specialty<select required value={form.specialty} onChange={(e) => setForm({ ...form, specialty: e.target.value })} className="input mt-1"><option value="">Select specialty</option><option>General Practice</option><option>Cardiology</option><option>Dermatology</option><option>Endocrinology</option><option>Gastroenterology</option><option>Neurology</option><option>Paediatrics</option><option>Psychiatry</option><option>Other</option></select></label>
        <label className="register-page__field register-page__field--wide">Primary practice setting<select required value={form.practiceSetting} onChange={(e) => setForm({ ...form, practiceSetting: e.target.value })} className="input mt-1"><option value="">Select practice setting</option><option>Clinic</option><option>Hospital</option><option>Independent practice</option><option>Telehealth</option><option>Other</option></select></label>
        <label className="register-page__field">Password<input required type="password" autoComplete="new-password" minLength="8" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="input mt-1" placeholder="Create a password" /></label>
        <label className="register-page__field">Confirm password<input required type="password" autoComplete="new-password" minLength="8" value={form.confirmPassword} onChange={(e) => setForm({ ...form, confirmPassword: e.target.value })} className="input mt-1" placeholder="Repeat password" /></label>
      </div><p className="register-page__password-note">Password: 8+ characters with a letter, number, and special character.</p>
      {error && <p role="alert" className="register-page__error">{error}</p>}<button className="register-page__submit" type="submit">Create account <ArrowRight size={17} /></button>
      <p className="register-page__login">Already have an account? <Link to="/login">Log in</Link></p>
    </motion.form></section>
  </div></main>
}
