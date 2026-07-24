import { LogOut, Moon, Sun, User } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'

export default function Header() {
  const { doctor, logout } = useAuth(); const { theme, toggleTheme } = useTheme(); const navigate = useNavigate()
  const leave = () => { logout(); navigate('/login') }
  return <header className="app-header fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between border-b border-border bg-card/95 px-4 shadow-sm backdrop-blur md:px-6 dark:border-slate-700 dark:bg-slate-800/95">
    <span className="text-lg font-bold text-primary">VitaNexus-RX</span>
    <div className="flex items-center gap-3">
      <div className="hidden items-center gap-2 sm:flex"><span className="grid h-8 w-8 place-items-center rounded-full bg-primary/10 text-primary"><User size={16} /></span><span className="text-sm font-semibold">{doctor?.name}</span></div>
      <button type="button" onClick={toggleTheme} aria-label="Toggle dark mode" className="grid h-9 w-9 place-items-center rounded-full border border-border transition hover:-translate-y-0.5 dark:border-slate-600">{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}</button>
      <button type="button" onClick={leave} className="btn-secondary px-3" aria-label="Log out"><LogOut size={16} /><span className="hidden sm:inline">Logout</span></button>
    </div>
  </header>
}
