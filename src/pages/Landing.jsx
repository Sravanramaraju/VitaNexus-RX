import { motion } from 'framer-motion'
import { ArrowRight, ShieldCheck } from 'lucide-react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Landing() {
  const { doctor } = useAuth(); if (doctor) return <Navigate to="/dashboard" replace />
  return <main className="landing-page grid min-h-screen place-items-center bg-background px-5 dark:bg-slate-900"><motion.section initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className="max-w-2xl text-center">
    <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-primary text-white shadow-md"><ShieldCheck size={28} /></span><p className="eyebrow mt-7">Clinical decision support</p>
    <h1 className="mt-3 text-4xl font-extrabold tracking-tight sm:text-6xl">VitaNexus-RX</h1><p className="mx-auto mt-5 max-w-xl text-lg leading-8 text-slate-600 dark:text-slate-300">Clear drug-interaction insights and patient follow-up workflows for clinicians.</p>
    <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row"><Link className="btn-primary" to="/register">Get Started <ArrowRight size={17} /></Link><Link className="btn-secondary" to="/login">Continue</Link></div>
  </motion.section></main>
}
