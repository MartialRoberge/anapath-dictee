// Bandeau « N actions recommandees » deployable, puis liste des actions.
import { useState } from "react";
import type { Recommandation } from "./types";

export function Recommandations({ recos }: { recos: Recommandation[] }) {
  const [ouvert, setOuvert] = useState(true);
  const n = recos.length;
  return (
    <section className="adm-carte adm-entree" style={{ borderColor: n ? "var(--adm-accent)" : undefined }} aria-label="Actions recommandées">
      <button type="button" className="flex w-full items-center justify-between bg-transparent p-0 text-left" aria-expanded={ouvert} onClick={() => setOuvert(!ouvert)}>
        <span className="adm-serif text-[24px]">{n === 0 ? "Aucune action recommandée" : `${n} action${n > 1 ? "s" : ""} recommandée${n > 1 ? "s" : ""}`}</span>
        <span className="text-[12px]" style={{ color: "var(--adm-doux)" }}>{ouvert ? "Masquer" : "Afficher"}</span>
      </button>
      {ouvert && n > 0 && (
        <ol className="m-0 mt-4 list-none divide-y p-0" style={{ borderColor: "var(--adm-filet)" }}>
          {recos.map((r) => (
            <li key={r.id} className="grid gap-1 py-3 sm:grid-cols-[110px_1fr]" style={{ borderColor: "var(--adm-filet)" }}>
              <span className="adm-label" style={{ color: r.severite === "critique" ? "var(--adm-accent)" : undefined }}>{r.severite}</span>
              <div>
                <div className="text-[14px] font-medium">{r.titre}</div>
                <div className="text-[13px]" style={{ color: "var(--adm-doux)" }}>{r.detail}</div>
              </div>
            </li>
          ))}
        </ol>
      )}
      {ouvert && n === 0 && <p className="m-0 mt-2 text-[13px]" style={{ color: "var(--adm-doux)" }}>Pas assez de données ou aucun seuil dépassé sur la période.</p>}
    </section>
  );
}
