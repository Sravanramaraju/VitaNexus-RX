import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useAuth } from './AuthContext'
import { addPatient, deletePatient, getNextPatientId, getPatients, updatePatient } from '../lib/storage'
import { generateConfidence, generateRecommendations, generateRiskResult, generateUpdatedRecommendations } from '../lib/mockEngine'

const PatientContext = createContext(null)
const makeVisit = (consultationInfo) => ({
  id: crypto.randomUUID(), date: new Date().toISOString(), prescribedDrug: consultationInfo.prescribedDrug,
  diagnosis: consultationInfo.diagnosis || '', doctorNotes: consultationInfo.doctorNotes || '',
  riskResult: generateRiskResult(), confidence: generateConfidence(), recommendations: generateRecommendations(),
  feedback: null, updatedRecommendations: null, status: 'in-progress',
})

export function PatientProvider({ children }) {
  const { doctor } = useAuth()
  const [patients, setPatients] = useState([])
  const [activeVisitId, setActiveVisitId] = useState(null)
  const refreshPatients = useCallback(() => setPatients(doctor ? getPatients(doctor.id) : []), [doctor])
  useEffect(() => { refreshPatients(); setActiveVisitId(null) }, [refreshPatients])

  const createPatient = (basicInfo, clinicalInfo, consultationInfo) => {
    const visit = makeVisit(consultationInfo)
    const patient = { id: getNextPatientId(), doctorId: doctor.id, ...basicInfo, ...clinicalInfo, visits: [visit], createdAt: new Date().toISOString() }
    addPatient(patient); refreshPatients(); setActiveVisitId(visit.id); return patient
  }
  const addVisitToPatient = (patientId, consultationInfo) => {
    const visit = makeVisit(consultationInfo)
    const updated = updatePatient(patientId, (patient) => ({ ...patient, visits: [...patient.visits, visit] }))
    refreshPatients(); setActiveVisitId(visit.id); return { patient: updated, visit }
  }
  const editPatient = (patientId, basicInfo, clinicalInfo) => { updatePatient(patientId, (patient) => ({ ...patient, ...basicInfo, ...clinicalInfo })); refreshPatients() }
  const deletePatientById = (patientId) => { deletePatient(patientId); refreshPatients() }
  const submitFeedback = (patientId, visitId, feedback) => {
    const updated = updatePatient(patientId, (patient) => ({ ...patient, visits: patient.visits.map((visit) => {
      if (visit.id !== visitId) return visit
      if (visit.status === 'completed') {
        const furtherFollowUp = { id: crypto.randomUUID(), date: new Date().toISOString(), ...feedback }
        return { ...visit, followUps: [...(visit.followUps || []), furtherFollowUp], updatedRecommendations: generateUpdatedRecommendations(feedback, visit.updatedRecommendations?.length ? visit.updatedRecommendations : visit.recommendations) }
      }
      return { ...visit, feedback, updatedRecommendations: generateUpdatedRecommendations(feedback, visit.recommendations), status: 'completed' }
    }) }))
    refreshPatients(); return updated
  }
  const saveVisitNotes = (patientId, visitId, doctorNotes) => { updatePatient(patientId, (patient) => ({ ...patient, visits: patient.visits.map((visit) => visit.id === visitId ? { ...visit, doctorNotes } : visit) })); refreshPatients() }

  return <PatientContext.Provider value={{ patients, refreshPatients, createPatient, addVisitToPatient, editPatient, deletePatientById, submitFeedback, saveVisitNotes, activeVisitId, setActiveVisitId }}>{children}</PatientContext.Provider>
}

export const usePatient = () => {
  const value = useContext(PatientContext)
  if (!value) throw new Error('usePatient must be used within PatientProvider')
  return value
}
