import { createContext, useContext, useEffect, useState } from 'react'
import { getTheme, setTheme } from '../lib/storage'

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(getTheme())
  useEffect(() => { document.documentElement.classList.toggle('dark', theme === 'dark') }, [theme])
  const toggleTheme = () => setThemeState((current) => {
    const next = current === 'dark' ? 'light' : 'dark'; setTheme(next); return next
  })
  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>
}
export const useTheme = () => {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used within ThemeProvider')
  return value
}
