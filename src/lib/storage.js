const read = (key, fallback) => {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
};
const write = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* localStorage unavailable */
  }
};

export const getDoctors = () => read("mrx_doctors", []);
export const saveDoctors = (list) => write("mrx_doctors", list);
export const getCurrentDoctor = () => read("mrx_current_doctor", null);
export const setCurrentDoctor = (doctor) => write("mrx_current_doctor", doctor);
export const getAllPatients = () => read("mrx_patients", []);
export const savePatients = (list) => write("mrx_patients", list);
export const getPatients = (doctorId) =>
  getAllPatients().filter((patient) => patient.doctorId === doctorId);
export const getPatientById = (patientId) =>
  getAllPatients().find((patient) => patient.id === patientId) || null;
export const addPatient = (patient) =>
  savePatients([...getAllPatients(), patient]);
export const updatePatient = (patientId, updaterFn) => {
  const list = getAllPatients();
  const index = list.findIndex((patient) => patient.id === patientId);
  if (index === -1) return null;
  const updated = updaterFn({ ...list[index] });
  list[index] = updated;
  savePatients(list);
  return updated;
};
export const deletePatient = (patientId) =>
  savePatients(getAllPatients().filter((patient) => patient.id !== patientId));
export const getNextPatientId = () => {
  try {
    const next = Number(localStorage.getItem("mrx_patient_counter") || 0) + 1;
    localStorage.setItem("mrx_patient_counter", String(next));
    return `P-${String(next).padStart(4, "0")}`;
  } catch {
    return `P-${String(Date.now()).slice(-4)}`;
  }
};
export const getTheme = () => {
  try {
    return localStorage.getItem("mrx_theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
};
export const setTheme = (theme) => {
  try {
    localStorage.setItem("mrx_theme", theme);
  } catch {
    /* localStorage unavailable */
  }
};

const intakeDraftKey = (existingPatientId) =>
  `mrx_patient_intake_draft_${existingPatientId || "new"}`;
export const getPatientIntakeDraft = (existingPatientId) =>
  read(intakeDraftKey(existingPatientId), null);
export const savePatientIntakeDraft = (existingPatientId, draft) =>
  write(intakeDraftKey(existingPatientId), draft);
export const clearPatientIntakeDraft = (existingPatientId) => {
  try {
    localStorage.removeItem(intakeDraftKey(existingPatientId));
  } catch {
    /* localStorage unavailable */
  }
};
