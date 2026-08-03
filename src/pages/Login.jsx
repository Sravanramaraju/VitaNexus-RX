import { motion } from 'framer-motion'
import { ArrowRight, FlaskConical, ShieldCheck, Stethoscope } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { doctor, login } = useAuth(); const navigate = useNavigate(); const [form, setForm] = useState({ email: '', password: '' }); const [error, setError] = useState('')
  if (doctor) return <Navigate to="/dashboard" replace />
  const submit = (event) => { event.preventDefault(); setError(''); try { login(form.email, form.password); navigate('/dashboard') } catch (err) { setError(err.message) } }
  return <main className="login-page"><div className="login-page__shell">
    <header className="login-page__header"><div className="login-page__brand"><span><Stethoscope size={17} /></span>VitaNexus-RX</div><p>Clinical decision support</p></header>
    <section className="login-page__content"><div className="login-page__intro"><span className="login-page__intro-icon"><FlaskConical size={23} /></span><p>Connected clinical intelligence</p><h1>Bring every patient interaction into focus.</h1><span>Continue to your workspace for structured medication review and informed follow-up.</span></div>
      <motion.form initial={{ opacity: 0, x: 22 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, ease: 'easeOut' }} onSubmit={submit} className="login-page__form"><span className="login-page__form-icon"><ShieldCheck size={21} /></span><div className="login-page__form-heading"><p>Secure sign in</p><h1>Welcome back</h1><span>Enter your details to continue.</span></div><div className="login-page__fields">
        <label className="login-page__field">Professional email<input required type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="input mt-1" placeholder="you@hospital.com" /></label>
        <label className="login-page__field">Password<input required type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="input mt-1" placeholder="Enter your password" /></label>
      </div>{error && <p role="alert" className="login-page__error">{error}</p>}<button className="login-page__submit" type="submit">Continue to workspace <ArrowRight size={17} /></button>
      <p className="login-page__register">New to VitaNexus-RX? <Link to="/register">Create an account</Link></p>
    </motion.form></section>
  </div></main>
}
