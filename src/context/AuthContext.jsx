import { createContext, useContext, useState } from 'react'
import { getCurrentDoctor, getDoctors, saveDoctors, setCurrentDoctor } from '../lib/storage'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [doctor, setDoctor] = useState(getCurrentDoctor())

  const register = (name, email, password) => {
    const doctors = getDoctors()
    if (doctors.some((item) => item.email.toLowerCase() === email.toLowerCase())) throw new Error('Email already registered')
    const newDoctor = { id: crypto.randomUUID(), name, email, password }
    saveDoctors([...doctors, newDoctor]); setCurrentDoctor(newDoctor); setDoctor(newDoctor)
    return newDoctor
  }
  const login = (email, password) => {
    const matched = getDoctors().find((item) => item.email.toLowerCase() === email.toLowerCase() && item.password === password)
    if (!matched) throw new Error('Invalid credentials')
    setCurrentDoctor(matched); setDoctor(matched); return matched
  }
  const logout = () => { setCurrentDoctor(null); setDoctor(null) }

  return <AuthContext.Provider value={{ doctor, register, login, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
