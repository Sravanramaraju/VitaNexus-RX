import { motion } from 'framer-motion'
import { ArrowRight, ShieldCheck, Sparkles, Stethoscope } from 'lucide-react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Landing() {
  const { doctor } = useAuth(); if (doctor) return <Navigate to="/dashboard" replace />
  return <main className="landing-page min-h-screen">
    <div className="landing-page__shell">
      <header className="landing-page__header">
        <div className="landing-page__brand"><span className="landing-page__brand-mark"><Stethoscope size={17} /></span><span>VitaNexus-RX</span></div>
        <span className="landing-page__header-label">Clinical decision support</span>
      </header>

      <motion.section initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: 'easeOut' }} className="landing-page__hero">
        <div className="landing-page__icon"><ShieldCheck size={29} /></div>
        <p className="landing-page__eyebrow"><Sparkles size={14} />Intelligent clinical workflow</p>
        <h1>Clinical clarity,<br /><span>when every decision counts.</span></h1>
        <p className="landing-page__description">Bring drug-interaction insights, patient context, and follow-up workflows into one focused workspace for clinicians.</p>
        <div className="landing-page__pills"><span>Drug interaction review</span><span>Patient follow-up</span></div>
        <div className="landing-page__actions"><Link className="landing-page__primary-action" to="/register">Get started <ArrowRight size={18} /></Link><Link className="landing-page__secondary-action" to="/login">Continue</Link></div>
      </motion.section>

      <p className="landing-page__footer">Designed for focused, informed clinical conversations.</p>
    </div>
  </main>
}
