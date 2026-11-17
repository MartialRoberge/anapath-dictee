// Codes ADICAP + SNOMED CT (+ CIM-O 3) : statut, confiance, copier, modifier. Un code incertain reste visible comme tel.
import { useState } from "react";
import { copierTexte } from "../lib/copy";
import { codeAffiche, type ProjetLocal } from "../lib/session";
import type { Code, SourceRef } from "../types";
import { ListeSources } from "./Source";

const SYSTEMES: Array<{ cle: Code["systeme"]; titre: string }> = [
  { cle: "ADICAP", titre: "ADICAP" },
  { cle: "SNOMED_CT", titre: "SNOMED CT" },
  { cle: "CIM_O3", titre: "CIM-O 3" },
];
const STATUT: Record<Code["statut"], { texte: string; classe: string }> = {
  certain: { texte: "Certain", classe: "text-[var(--ink)] font-medium" },
  partiel: { texte: "Partiel", classe: "text-[var(--mute)]" },
  suggestion: { texte: "Suggestion à confirmer", classe: "text-[var(--amber)]" },
};

interface Props {
  local: ProjetLocal;
  onCopie: (c: Code, texte: string) => void;
  onModifier: (c: Code, nouveau: string) => void;
  onNotifier: (m: string) => void;
  onConsulte?: (s: SourceRef) => void;
}

function Ligne({ c, affiche, onCopie, onModifier, onConsulte }: { c: Code; affiche: string; onCopie: Props["onCopie"]; onModifier: Props["onModifier"]; onConsulte?: Props["onConsulte"] }) {
  const [edition, setEdition] = useState(false);
  const [valeur, setValeur] = useState(affiche);
  const s = STATUT[c.statut];
  return (
    <li className="enter rounded-xl border border-[var(--line)] bg-white px-4 py-3.5">
      <div className="flex items-baseline gap-3">
        {edition ? (
          <form className="flex flex-1 items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (valeur.trim()) { onModifier(c, valeur.trim()); setEdition(false); } }}>
            <input autoFocus value={valeur} onChange={(e) => setValeur(e.target.value)} aria-label={`Code ${c.systeme}`} onKeyDown={(e) => e.key === "Escape" && setEdition(false)}
              className="num h-8 w-full rounded-md border border-[var(--line)] px-2 text-[14px] font-medium champ" />
            <button type="submit" className="btn btn-sm">OK</button>
          </form>
        ) : (
          <span className="num text-[15px] font-semibold tracking-wide">{affiche}{affiche !== c.code && <span className="ml-2 text-[11px] font-normal text-[var(--faint)]">modifié</span>}</span>
        )}
        <span className="num ml-auto text-[12px] text-[var(--faint)]">{Math.round(c.confiance * 100)} %</span>
      </div>
      <p className="mt-1 text-[13.5px] leading-snug">{c.libelle}</p>
      <p className={`mt-1 text-[12px] ${s.classe}`}>{s.texte}</p>
      {c.explication && <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--mute)]">{c.explication}</p>}
      <ListeSources sources={c.sources} onConsulte={onConsulte} />
      <div className="mt-3 flex gap-1.5">
        <button type="button" className="btn btn-sm" onClick={() => onCopie(c, affiche)}>Copier</button>
        {!edition && <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setValeur(affiche); setEdition(true); }}>Modifier</button>}
      </div>
    </li>
  );
}

export default function OngletCodes({ local, onCopie, onModifier, onNotifier, onConsulte }: Props) {
  const codes = local.projet.codes;
  if (codes.length === 0) {
    return <p className="px-5 py-6 text-[13.5px] leading-relaxed text-[var(--mute)]">Aucun code proposé. Mieux vaut l'absence de code qu'un code inventé : codez manuellement si besoin.</p>;
  }
  return (
    <div className="space-y-6 px-5 py-5">
      {SYSTEMES.map(({ cle, titre }) => {
        const liste = codes.filter((c) => c.systeme === cle);
        if (!liste.length) return null;
        return (
          <section key={cle} aria-label={titre}>
            <h3 className="label mb-2.5">{titre}</h3>
            <ul className="space-y-2.5">{liste.map((c) => <Ligne key={`${c.systeme}${c.code}`} c={c} affiche={codeAffiche(local, c)} onCopie={onCopie} onModifier={onModifier} onConsulte={onConsulte} />)}</ul>
          </section>
        );
      })}
      <button type="button" className="btn btn-sm" onClick={async () => {
        const t = codes.map((c) => `${c.systeme.replace("_", " ")} ${codeAffiche(local, c)} ${c.libelle}`).join("\n");
        onNotifier((await copierTexte(t)) ? "Codes copiés" : "Copie impossible");
      }}>Copier tous les codes</button>
    </div>
  );
}
