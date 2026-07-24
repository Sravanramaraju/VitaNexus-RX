import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Register() {
  const { doctor, register } = useAuth(); const navigate = useNavigate(); const [form, setForm] = useState({ name: '', email: '', password: '' }); const [error, setError] = useState('')
  if (doctor) return <Navigate to="/dashboard" replace />
  const submit = (event) => { event.preventDefault(); setError(''); try { register(form.name, form.email, form.password); navigate('/dashboard') } catch (err) { setError(err.message) } }
  return <main className="auth-page grid min-h-screen place-items-center bg-background p-5 dark:bg-slate-900"><form onSubmit={submit} className="surface w-full max-w-md p-7"><p className="eyebrow">VitaNexus-RX</p><h1 className="mt-2 text-2xl font-bold">Create your account</h1><div className="mt-6 space-y-4">
    <label className="block text-sm font-semibold">Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input mt-1" /></label>
    <label className="block text-sm font-semibold">Email<input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="input mt-1" /></label>
    <label className="block text-sm font-semibold">Password<input required type="password" minLength="4" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="input mt-1" /></label>
    {error && <p className="rounded-lg bg-danger/10 p-3 text-sm text-danger">{error}</p>}<button className="btn-primary w-full" type="submit">Register</button>
  </div><p className="mt-5 text-center text-sm text-slate-600 dark:text-slate-300">Already registered? <Link className="font-bold text-primary" to="/login">Log in</Link></p></form></main>
}
