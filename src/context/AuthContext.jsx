import { createContext, useContext, useEffect, useState } from 'react'
import { api, apiJson, getAccessToken, setAccessToken } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [doctor, setDoctor] = useState(null)
  useEffect(() => {
    const clearSession = () => { setAccessToken(null); setDoctor(null); };
    window.addEventListener("vitanexus-auth-invalid", clearSession);
    if (getAccessToken()) api('/auth/me').then(setDoctor).catch(clearSession);
    return () => window.removeEventListener("vitanexus-auth-invalid", clearSession);
  }, [])

  const register = async (name, email, password, profile = {}) => {
    const result = await apiJson('/auth/register', 'POST', { name, email, password, ...profile })
    setAccessToken(result.accessToken); setDoctor(result.clinician); return result.clinician
  }
  const login = async (email, password) => {
    const result = await apiJson('/auth/login', 'POST', { email, password })
    setAccessToken(result.accessToken); setDoctor(result.clinician); return result.clinician
  }
  const logout = async () => { try { await apiJson('/auth/logout', 'POST', {}) } finally { setAccessToken(null); setDoctor(null) } }

  return <AuthContext.Provider value={{ doctor, register, login, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
