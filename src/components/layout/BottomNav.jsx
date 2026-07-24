import { CheckCircle2, Clock3, LayoutDashboard } from "lucide-react";
import { NavLink, useParams } from "react-router-dom";
import { usePatient } from "../../context/PatientContext";

export default function BottomNav() {
  const { patientId } = useParams();
  const { patients, activeVisitId, setActiveVisitId } = usePatient();
  const patient = patients.find((item) => item.id === patientId);
  return (
    <nav className="app-bottom-nav fixed inset-x-0 bottom-0 z-40 flex h-16 items-center gap-1 overflow-x-auto border-t border-border bg-card px-2 shadow-md md:hidden dark:border-slate-700 dark:bg-slate-800">
      {!patient ? (
        <NavLink
          to="/dashboard"
          className="mx-auto flex items-center gap-2 text-sm font-bold text-primary"
        >
          <LayoutDashboard size={17} />
          Dashboard
        </NavLink>
      ) : (
        patient.visits.map((visit, index) => (
          <button
            type="button"
            onClick={() => setActiveVisitId(visit.id)}
            key={visit.id}
            className={`flex min-w-20 flex-1 flex-col items-center text-xs font-semibold ${activeVisitId === visit.id ? "text-primary" : "text-slate-500"}`}
          >
            {visit.status === "completed" ? (
              <CheckCircle2 size={17} className="text-success" />
            ) : (
              <Clock3 size={17} className="text-warning" />
            )}
            <span>Visit {index + 1}</span>
          </button>
        ))
      )}
    </nav>
  );
}
