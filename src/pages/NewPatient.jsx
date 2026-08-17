import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronLeft, ChevronRight, Pencil, Plus, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import ExplainToggle from "../components/shared/ExplainToggle";
import { usePatient } from "../context/PatientContext";
import {
  ALLERGY_SEVERITY_OPTIONS,
  COMMON_ALLERGIES,
  COMMON_DISEASES,
  EXTENDED_ALLERGIES,
  EXTENDED_DISEASES,
} from "../data/clinicalOptions";
import { getDrugSelectionReasons } from "../lib/explainability";
import { resolveDrugInput, searchCondition } from "../lib/otcMapping";
import { useTerminologySearch } from "../hooks/useTerminologySearch";
import {
  clearPatientIntakeDraft,
  getPatientIntakeDraft,
  savePatientIntakeDraft,
} from "../lib/storage";

const frequencyHelp = [
  ["1d", "Once Daily"], ["2d", "Twice Daily"], ["3d", "Three Times Daily"],
  ["1w", "Once Weekly"], ["2w", "Twice Weekly"], ["3w", "Three Times Weekly"],
];
const isValidFrequency = (value) => /^(1d|2d|3d|1w|2w|3w)$/.test(value.replace(/\s/g, ""));
const allergyAlertClass = {
  Mild: "border-warning bg-warning/15 text-slate-900",
  Moderate: "border-orange-500 bg-orange-500/15 text-orange-700 dark:text-orange-300",
  Severe: "border-danger bg-danger/15 text-danger",
};

function IndicationAutocomplete({ value, onChange }) {
  const [query, setQuery] = useState(value || "");
  const [open, setOpen] = useState(false);
  const { items: matches, error } = useTerminologySearch("indications", query);

  useEffect(() => setQuery(value || ""), [value]);

  return <div className="relative"><label className="block text-sm font-semibold">Diagnosis / Treatment Indication <span className="text-danger">*</span></label><input className="input mt-1" value={query} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => { setOpen(false); if (!value) setQuery(""); }, 150)} onChange={(event) => { setQuery(event.target.value); setOpen(true); onChange(""); }} placeholder="Type one or more letters, e.g. D or De" aria-autocomplete="list" aria-required="true" />{open && query && <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-md dark:border-slate-600 dark:bg-slate-800">{error ? <p className="px-3 py-2 text-xs text-danger">Lookup unavailable: {error}</p> : matches.length ? matches.map((option) => <button type="button" key={option.normalizedName} className="block w-full px-3 py-2 text-left text-sm hover:bg-primary/10" onMouseDown={(event) => event.preventDefault()} onClick={() => { onChange(option.display); setQuery(option.display); setOpen(false) }}>{option.display}<span className="block text-xs text-slate-500">{option.source}</span></button>) : <p className="px-3 py-2 text-xs text-slate-500">No matching dataset indication</p>}</div>}<p className="mt-1 text-xs text-slate-500">Type a prefix to narrow real DrugCentral indications; up to 30 choices are shown.</p></div>
}

function CurrentMedicationList({ items = [], onChange }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [dosage, setDosage] = useState("");
  const [frequency, setFrequency] = useState("");
  const [warning, setWarning] = useState("");
  const [editingIndex, setEditingIndex] = useState(null);
  const { items: matches, error } = useTerminologySearch("medications", query);
  const add = () => {
    const drugName = selected?.genericName || selected?.brand || query.trim();
    if (!drugName) return setWarning("Enter or select a medicine before adding it.");
    if (items.some((item) => (item.drugName || item.generic || item.brand).toLowerCase() === drugName.toLowerCase())) return setWarning(`${drugName} is already in the current medication list.`);
    const resolved = resolveDrugInput(selected ? { ...selected, generic: selected.genericName } : { brand: query.trim(), generic: drugName });
    onChange([...items, { drugName, enteredName: resolved.enteredName, normalizedName: resolved.normalizedName, brand: resolved.brand || drugName, generic: resolved.generic || drugName, mappingSource: resolved.mappingSource, mappingVersion: resolved.mappingVersion, dosage: dosage.trim(), frequency: frequency.trim(), activeStatus: "active" }]);
    setQuery(""); setSelected(null); setDosage(""); setFrequency(""); setWarning("");
  };
  const editing = editingIndex === null ? null : items[editingIndex];
  const updateMedication = (changes) => onChange(items.map((item, index) => index === editingIndex ? { ...item, ...changes } : item));
  return <div className="space-y-3"><div className="relative"><input className="input" value={selected ? `${selected.brand} (${selected.genericName})` : query} onChange={(event) => { setSelected(null); setQuery(event.target.value); setWarning(""); }} placeholder="Type a brand or generic name" />{query && !selected && <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-md dark:border-slate-600 dark:bg-slate-800">{error ? <p className="px-3 py-2 text-xs text-danger">Lookup unavailable: {error}</p> : matches.length ? matches.map((item) => <button type="button" key={item.id} onClick={() => { setSelected(item); setQuery(""); setWarning(""); }} className="block w-full px-3 py-2 text-left text-sm hover:bg-primary/10"><strong>{item.brand}</strong><span className="block text-xs text-slate-500">Generic: {item.genericName} · {item.mappingSource}</span></button>) : <p className="px-3 py-2 text-xs text-slate-500">No matching Indian brand or generic medicine</p>}</div>}</div><div className="grid gap-2 sm:grid-cols-3"><input className="input" value={dosage} onChange={(event) => setDosage(event.target.value)} placeholder="Dosage (optional)" /><input className="input" value={frequency} onChange={(event) => setFrequency(event.target.value)} placeholder="Frequency (optional)" /><button type="button" className="btn-secondary" onClick={add}>Add medication</button></div>{warning && <p role="alert" className="text-xs font-medium text-warning">{warning}</p>}<p className="text-xs text-slate-500">Start with one letter; both Indian brand and generic-name matches are shown.</p>{items.length > 0 && <div className="space-y-2">{items.map((item, index) => <div key={`${item.drugName || item.brand}-${index}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-700/50"><span><strong>Entered name: {item.enteredName || item.brand}</strong> · Generic name: {item.generic || item.drugName}<small className="block text-xs text-slate-500">Mapping source: {item.mappingSource || "Indian Medicine Dataset"}</small></span><div className="flex items-center gap-2"><select className="input py-1 text-xs" value={item.activeStatus || "active"} onChange={(event) => onChange(items.map((entry, entryIndex) => entryIndex === index ? { ...entry, activeStatus: event.target.value } : entry))}><option value="active">Active</option><option value="completed">Completed</option><option value="discontinued">Discontinued</option></select><button type="button" className="rounded p-1 text-primary hover:bg-primary/10" onClick={() => setEditingIndex(index)} aria-label={`Edit ${item.drugName || item.brand}`}><Pencil size={15} /></button><button type="button" className="text-xs font-semibold text-danger" onClick={() => onChange(items.filter((_, entryIndex) => entryIndex !== index))}>Remove</button></div></div>)}</div>}{editing && <div className="rounded-lg border border-primary/30 p-3"><p className="text-sm font-semibold">Edit {editing.drugName || editing.brand}</p><div className="mt-2 grid gap-2 sm:grid-cols-2"><label className="text-xs font-semibold">Dosage<input className="input mt-1" value={editing.dosage || ""} onChange={(event) => updateMedication({ dosage: event.target.value })} /></label><label className="text-xs font-semibold">Frequency<input className="input mt-1" value={editing.frequency || ""} onChange={(event) => updateMedication({ frequency: event.target.value })} /></label></div><button type="button" className="btn-secondary mt-3" onClick={() => setEditingIndex(null)}>Done</button></div>}</div>
}

const prescriptionToMedication = (visit) => {
  const medicine = visit.prescription?.medicine || visit.prescribedDrug;
  if (!medicine) return null;
  return {
    drugName: medicine.generic || medicine.brand,
    brand: medicine.brand,
    generic: medicine.generic,
    dosage: visit.prescription?.dosage || "",
    frequency: visit.prescription?.frequency || "",
    activeStatus: "active",
  };
};

const getCurrentMedicationsForConsultation = (patient) =>
  [...(patient.currentMedications || []), ...(patient.visits || [])
    .map(prescriptionToMedication)
    .filter(Boolean)]
    .reduce((medications, medication) => {
      const name = (
        medication.drugName || medication.generic || medication.brand || ""
      ).toLowerCase();
      const alreadyIncluded = medications.some(
        (item) =>
          (item.drugName || item.generic || item.brand || "").toLowerCase() ===
          name,
      );
      return alreadyIncluded ? medications : [...medications, medication];
    }, []);

function ConditionPanel({ title, common, extended, kind, entries, onChange }) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [detail, setDetail] = useState(kind === "allergy" ? "Mild" : "");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedDatasetCondition, setSelectedDatasetCondition] = useState(null);
  const detailRef = useRef(null);
  const { items: datasetResults, error } = useTerminologySearch("conditions", kind === "disease" ? name : "");
  const results = kind === "disease" ? datasetResults : searchCondition(name, extended);
  const has = (condition) =>
    entries.some(
      (entry) => entry.name.toLowerCase() === condition.toLowerCase(),
    );
  const updateDetail = (condition, value) =>
    onChange(
      entries.map((entry) =>
        entry.name === condition
          ? { ...entry, [kind === "allergy" ? "severity" : "duration"]: value }
          : entry,
      ),
    );
  const changeCommon = (condition, checked) =>
    checked
      ? onChange([...entries, kind === "allergy" ? { name: condition, severity: "Mild", isCustom: false } : { name: condition, duration: "", isCustom: false }])
      : onChange(entries.filter((entry) => entry.name !== condition));
  const addOther = () => {
    const finalName = name.trim();
    if (!finalName) return;
    const commonName = common.find(
      (item) => item.toLowerCase() === finalName.toLowerCase(),
    );
    const extendedName = extended.find(
      (item) => item.toLowerCase() === finalName.toLowerCase(),
    );
    const recognized = commonName || extendedName;
    const selectedCondition = kind === "disease" && selectedDatasetCondition?.display === finalName ? selectedDatasetCondition : null;
    const diseaseEntry = (display) => ({ name: display, duration: detail, isCustom: !selectedCondition, code: selectedCondition?.code || null, source: selectedCondition?.source || "clinician-entered" });
    if (commonName && !has(commonName))
      onChange([...entries, kind === "allergy" ? { name: commonName, severity: detail, isCustom: false } : { name: commonName, duration: detail, isCustom: false }]);
    else if (!has(recognized || finalName))
      onChange([
        ...entries,
        kind === "allergy" ? { name: recognized || finalName, severity: detail, isCustom: !recognized } : diseaseEntry(recognized || finalName),
      ]);
    else if (has(recognized || finalName))
      updateDetail(recognized || finalName, detail);
    setName("");
    setDetail(kind === "allergy" ? "Mild" : "");
    setSelectedDatasetCondition(null);
    setShowSuggestions(false);
  };
  return (
    <article className="surface p-5">
      <h2 className="font-bold">{title}</h2>
      <div className="mt-4 space-y-3">
        {common.map((condition) => {
          const entry = entries.find((item) => item.name === condition);
          return (
            <div
              key={condition}
              className="rounded-lg bg-slate-50 p-2.5 dark:bg-slate-700/50"
            >
              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  checked={Boolean(entry)}
                  onChange={(e) => changeCommon(condition, e.target.checked)}
                />
                {condition}
              </label>
              {entry &&
                (kind === "allergy" ? (
                  <select
                    value={entry.severity || entry.detail || "Mild"}
                    onChange={(e) => updateDetail(condition, e.target.value)}
                    className={`input mt-2 py-1.5 text-xs ${allergyAlertClass[entry.severity || entry.detail || "Mild"]}`}
                  >
                    {ALLERGY_SEVERITY_OPTIONS.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="input mt-2 py-1.5 text-xs"
                    placeholder="Disease duration, e.g. 5 yrs"
                    value={entry.duration || entry.detail || ""}
                    onChange={(e) => updateDetail(condition, e.target.value)}
                  />
                ))}
            </div>
          );
        })}
      </div>
      <button
        type="button"
        onClick={() => setAdding(!adding)}
        className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary"
      >
        <Plus size={15} />
        Add other condition
      </button>
      {adding && (
        <div className="mt-3 rounded-lg border border-dashed border-primary/40 p-3">
          <div className="relative">
            <input
              className="input"
              placeholder="Search or enter a condition"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setSelectedDatasetCondition(null);
                setShowSuggestions(true);
              }}
            />
            {showSuggestions && name && (
              <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-md dark:border-slate-600 dark:bg-slate-800">
                {results.length ? results.map((result) => (
                  <button
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm hover:bg-primary/10"
                    onClick={() => {
                      const display = kind === "disease" ? result.display : result;
                      setName(display);
                      setSelectedDatasetCondition(kind === "disease" ? result : null);
                      setShowSuggestions(false);
                      requestAnimationFrame(() => detailRef.current?.focus());
                    }}
                    key={kind === "disease" ? result.diseaseIdentity || result.normalizedName : result}
                  >
                    {kind === "disease" ? <><strong>{result.display}</strong><span className="block text-xs text-slate-500">{result.source}{result.code ? ` · ${result.code}` : ""}</span></> : result}
                  </button>
                )) : <p className={`px-3 py-2 text-xs ${error ? "text-danger" : "text-slate-500"}`}>{error ? `Lookup unavailable: ${error}` : "No matching dataset disease"}</p>}
              </div>
            )}
          </div>
          <div className="mt-2 flex gap-2">
            {kind === "allergy" ? (
              <select
                ref={detailRef}
                className="input"
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
              >
                {ALLERGY_SEVERITY_OPTIONS.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            ) : (
              <input
                ref={detailRef}
                className="input"
                value={detail}
                placeholder="Duration"
                onChange={(e) => setDetail(e.target.value)}
              />
            )}
            <button
              type="button"
              onClick={addOther}
              className="btn-secondary shrink-0 px-3"
            >
              Add
            </button>
          </div>
        </div>
      )}
      {entries.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {entries.map((entry) => (
            <div key={entry.name} className="max-w-full">
              <span className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium ${kind === "allergy" ? allergyAlertClass[entry.severity || entry.detail || "Mild"] : "border-primary/20 bg-primary/10 text-primary"}`}>
                {entry.name} —{" "}
                {kind === "allergy"
                  ? entry.severity || entry.detail || "Mild"
                  : entry.duration || entry.detail || "Not specified"}
                <button
                  type="button"
                  onClick={() =>
                    onChange(entries.filter((item) => item.name !== entry.name))
                  }
                  aria-label={`Remove ${entry.name}`}
                >
                  <X size={13} />
                </button>
              </span>
              {entry.isCustom && (
                <p className="mt-1 text-[10px] text-warning">
                  Custom entries have limited AI analysis
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function PrescribedDrug({ value, onChange }) {
  const [query, setQuery] = useState("");
  const { items: matches, error } = useTerminologySearch("medications", query);
  return (
    <div>
      <label className="text-sm font-semibold">Prescribed drug</label>
      <div className="relative mt-1">
        <input
          className="input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type a brand or generic name"
        />
        {query && (
          <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-md dark:border-slate-600 dark:bg-slate-800">
            {error ? <p className="px-3 py-2 text-xs text-danger">Lookup unavailable: {error}</p> : matches.length ? (
              matches.map((item) => (
                <button
                  type="button"
                  key={item.brand}
                  onClick={() => {
                    onChange(resolveDrugInput({ ...item, generic: item.genericName }));
                    setQuery("");
                  }}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-primary/10"
                >
                  <strong>{item.brand}</strong>
                  <span className="block text-xs text-slate-500">
                    Generic: {item.genericName}
                  </span>
                </button>
              ))
            ) : (
              <p className="px-3 py-2 text-xs text-slate-500">
                No matching brands
              </p>
            )}
          </div>
        )}
      </div>
      {value && (
        <div className="mt-3 rounded-lg bg-primary/10 p-3 text-sm text-primary">
          <span className="font-semibold">
            Entered drug name: {value.enteredName || value.brand} / Generic name: {value.generic} / Mapping source: {value.mappingSource || "Indian Medicine Dataset"}
          </span>
          <ExplainToggle reasons={getDrugSelectionReasons()} />
        </div>
      )}
    </div>
  );
}

export default function NewPatient() {
  const { patients, createPatient, addVisitToPatient, editPatient } = usePatient();
  const navigate = useNavigate();
  const location = useLocation();
  const existingPatientId = location.state?.existingPatientId;
  const existing = patients.find((item) => item.id === existingPatientId);
  const isPatientEdit = location.state?.mode === "edit" && Boolean(existing);
  const savedDraft = getPatientIntakeDraft(existingPatientId);
  const [step, setStep] = useState(savedDraft?.step || (isPatientEdit ? 1 : existing ? 2 : 1));
  const [basic, setBasic] = useState(
    savedDraft?.basic ||
      (existing
        ? { name: existing.name, age: existing.age, gender: existing.gender }
        : { name: "", age: "", gender: "" }),
  );
  const [clinical, setClinical] = useState(
    savedDraft?.clinical ||
      (existing
        ? {
            diseases: existing.diseases,
            allergies: existing.allergies,
            currentMedications: getCurrentMedicationsForConsultation(existing),
          }
        : { diseases: [], allergies: [], currentMedications: [] }),
  );
  const [consultation, setConsultation] = useState(
    savedDraft?.consultation || {
      prescription: { medicine: null, dosage: "", frequency: "" },
      indication: "",
      doctorNotes: "",
    },
  );
  useEffect(() => {
    savePatientIntakeDraft(existingPatientId, {
      step,
      basic,
      clinical,
      consultation,
    });
  }, [existingPatientId, step, basic, clinical, consultation]);
  const completeness = useMemo(
    () =>
      Math.round(
        ([
          clinical.diseases,
          clinical.allergies,
          clinical.currentMedications,
        ].filter((items) => items.length > 0).length /
          3) *
          100,
      ),
    [clinical],
  );
  const analyze = async () => {
    if (isPatientEdit) {
      await editPatient(existing.id, { ...basic, age: Number(basic.age) }, clinical);
      clearPatientIntakeDraft(existingPatientId);
      navigate("/dashboard");
      return;
    }
    if (!consultation.prescription?.medicine || !consultation.indication || !consultation.prescription.dosage.trim() || !isValidFrequency(consultation.prescription.frequency)) return;
    const result = existing
      ? await addVisitToPatient(existing.id, consultation)
      : await createPatient(
          { ...basic, age: Number(basic.age) },
          clinical,
          consultation,
        );
    const id = existing ? existing.id : result.patient.id;
    const visitId = result.visit.id;
    clearPatientIntakeDraft(existingPatientId);
    navigate(`/patients/${id}`, { state: { entry: "results", visitId } });
  };
  const stepContent =
    step === 1 ? (
      <div className="surface p-6">
        <h2 className="text-xl font-bold">Basic Details</h2>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <label className="text-sm font-semibold md:col-span-2">
            Name
            <input
              className="input mt-1"
              value={basic.name}
              onChange={(e) => setBasic({ ...basic, name: e.target.value })}
            />
          </label>
          <label className="text-sm font-semibold">
            Age
            <input
              type="number"
              className="input mt-1"
              value={basic.age}
              onChange={(e) => setBasic({ ...basic, age: e.target.value })}
            />
          </label>
          <label className="text-sm font-semibold md:col-span-3">
            Gender
            <select
              className="input mt-1"
              value={basic.gender}
              onChange={(e) => setBasic({ ...basic, gender: e.target.value })}
            >
              <option value="">Select gender</option>
              <option>Female</option>
              <option>Male</option>
              <option>Other</option>
            </select>
          </label>
        </div>
      </div>
    ) : step === 2 ? (
      <div>
        <div className="grid gap-5 lg:grid-cols-3">
          <ConditionPanel
            title="Diseases"
            common={COMMON_DISEASES}
            extended={EXTENDED_DISEASES}
            kind="disease"
            entries={clinical.diseases}
            onChange={(diseases) => setClinical({ ...clinical, diseases })}
          />
          <ConditionPanel
            title="Allergies"
            common={COMMON_ALLERGIES}
            extended={EXTENDED_ALLERGIES}
            kind="allergy"
            entries={clinical.allergies}
            onChange={(allergies) => setClinical({ ...clinical, allergies })}
          />
          <article className="surface p-5">
            <h2 className="font-bold">Current Medication</h2>
            <div className="mt-4">
              <CurrentMedicationList items={clinical.currentMedications} onChange={(currentMedications) => setClinical({ ...clinical, currentMedications })} />
              <p className="mt-2 text-xs text-slate-500">
                Dosage and frequency are optional for past medications. If
                known, dosage examples include 500 mg, 5 mL, 1 Tablet, and 2
                Capsules; common frequency codes are 1d, 2d, 3d, 1w, 2w, and
                3w.
              </p>
            </div>
          </article>
        </div>
        <div className="surface mt-5 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-4 text-sm">
            <span>
              <Check size={15} className="mr-1 inline text-accent" />
              Diseases: {clinical.diseases.length}
            </span>
            <span>
              <Check size={15} className="mr-1 inline text-accent" />
              Allergies: {clinical.allergies.length}
            </span>
            <span>
              <Check size={15} className="mr-1 inline text-accent" />
              Medicines: {clinical.currentMedications.length}
            </span>
          </div>
          <div className="min-w-56">
            <div className="flex justify-between text-xs font-semibold">
              <span>Profile Completeness</span>
              <span>{completeness}%</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-accent/15">
              <motion.div
                className="h-full bg-accent"
                animate={{ width: `${completeness}%` }}
                transition={{ duration: 0.3, ease: "easeInOut" }}
              />
            </div>
          </div>
        </div>
      </div>
    ) : (
      <div className="surface p-6">
        <h2 className="text-xl font-bold">Current Consultation</h2>
        <div className="mt-5 space-y-4">
          <PrescribedDrug
            value={consultation.prescription?.medicine}
            onChange={(medicine) => setConsultation({ ...consultation, prescription: { ...consultation.prescription, medicine } })}
          />
          <div className="grid gap-4 md:grid-cols-2"><label className="block text-sm font-semibold">Dosage <span className="text-danger">*</span><input className="input mt-1" placeholder="e.g. 500 mg, 5 mL, 1 Tablet, 2 Capsules" value={consultation.prescription?.dosage || ""} onChange={(event) => setConsultation({ ...consultation, prescription: { ...consultation.prescription, dosage: event.target.value } })} /></label><label className="block text-sm font-semibold">Frequency <span className="text-danger">*</span><input className={`input mt-1 ${(consultation.prescription?.frequency) && !isValidFrequency(consultation.prescription.frequency) ? "border-danger" : ""}`} placeholder="e.g. 1d" value={consultation.prescription?.frequency || ""} onChange={(event) => setConsultation({ ...consultation, prescription: { ...consultation.prescription, frequency: event.target.value } })} /><span className="mt-1 block text-xs font-normal text-slate-500">{frequencyHelp.map(([code, label]) => `${code} = ${label}`).join(" · ")}</span></label></div>
          <IndicationAutocomplete value={consultation.indication} onChange={(indication) => setConsultation({ ...consultation, indication })} />
          <label className="block text-sm font-semibold">
            Doctor Notes{" "}
            <span className="font-normal text-slate-500">(optional)</span>
            <textarea
              className="input mt-1 min-h-28"
              value={consultation.doctorNotes}
              onChange={(e) =>
                setConsultation({
                  ...consultation,
                  doctorNotes: e.target.value,
                })
              }
            />
          </label>
        </div>
      </div>
    );
  return (
    <section className="mx-auto max-w-6xl">
      <div className="mb-7">
        <p className="eyebrow">
          {isPatientEdit ? "Patient intake" : existing ? "New consultation" : "Patient intake"}
        </p>
        <h1 className="mt-1 text-3xl font-bold">
          {isPatientEdit ? `Edit patient: ${existing.name}` : existing ? `Consultation for ${existing.name}` : "Add New Patient"}
        </h1>
      </div>
      {(!existing || isPatientEdit) && (
        <div className="mb-7 flex items-center gap-2">
          {[1, 2, 3].map((number) => (
            <div key={number} className="flex items-center gap-2">
              <span
                className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${number === step ? "bg-primary text-white" : number < step ? "bg-accent text-white" : "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-200"}`}
              >
                {number}
              </span>
              <span className="hidden text-xs font-semibold sm:inline">
                Step {number}
              </span>
              {number < 3 && <span className="h-px w-6 bg-border" />}
            </div>
          ))}
        </div>
      )}
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, x: 18 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -18 }}
          transition={{ duration: 0.3, ease: "easeInOut" }}
        >
          {stepContent}
        </motion.div>
      </AnimatePresence>
      <div className="mt-6 flex justify-between">
        {step > (isPatientEdit ? 1 : existing ? 2 : 1) ? (
          <button className="btn-secondary" onClick={() => setStep(step - 1)}>
            <ChevronLeft size={16} />
            Back
          </button>
        ) : (
          <span />
        )}
        {step < (isPatientEdit ? 2 : 3) ? (
          <button
            className="btn-primary"
            disabled={
              step === 1 && (!basic.name || !basic.age || !basic.gender)
            }
            onClick={() => setStep(step + 1)}
          >
            Next <ChevronRight size={16} />
          </button>
        ) : (
          <button
            className="btn-primary"
            disabled={isPatientEdit ? false : !consultation.prescription?.medicine || !consultation.indication || !consultation.prescription.dosage?.trim() || !isValidFrequency(consultation.prescription.frequency || "")}
            onClick={analyze}
          >
            {isPatientEdit ? "Save patient changes" : "Save consultation"}
          </button>
        )}
      </div>
    </section>
  );
}
