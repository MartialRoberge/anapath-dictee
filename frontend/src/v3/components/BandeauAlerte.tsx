// Point à vérifier actif, rappelé au-dessus de la barre d'actions quand le panneau Raisonnement est replié (tablette).
import type { Alerte } from "../types";
import { touche } from "../lib/raccourcis";

interface Props { alerte: Alerte; reste: number; onDecider: (a: Alerte, d: "resolue" | "ignoree") => void }

export default function BandeauAlerte({ alerte, reste, onDecider }: Props) {
  return (
    <div role="status" className="enter flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-[var(--line)] bg-white px-4 py-2.5 min-[1180px]:hidden">
      <p className="min-w-0 flex-1 basis-[240px] text-[13px] leading-snug">
        <span className="label mr-2">{alerte.gravite === "bloquant" ? "Bloquant" : alerte.gravite === "attention" ? "Attention" : "Information"} · {reste}</span>
        {alerte.message}
      </p>
      <button type="button" className="btn btn-sm" onClick={() => onDecider(alerte, "resolue")}>Résoudre <span className="kbd">{touche("R")}</span></button>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => onDecider(alerte, "ignoree")}>Ignorer <span className="kbd">{touche("I")}</span></button>
    </div>
  );
}
