// Espace « Nouveau projet » : un seul geste pour dicter (Espace maintenu / bouton), ou coller le texte.
import { useEffect, useRef, useState } from "react";
import { dicteesExemples } from "../fixtures/projetPoumon";
import { estMac } from "../lib/raccourcis";
import BarreDictee from "./BarreDictee";

interface Props {
  occupe: boolean;
  etatMicro: "repos" | "demande" | "enregistre";
  secondes: number;
  onBasculerMicro: () => void;
  onAnnulerMicro: () => void;
  onTexte: (texte: string) => void;
  nom: string;
  brouillonInitial?: string;
}

const salutation = () => {
  const h = new Date().getHours();
  return h >= 18 || h < 5 ? "Bonsoir" : "Bonjour";
};

export default function NouveauProjet(p: Props) {
  const [texte, setTexte] = useState(p.brouillonInitial ?? "");
  const zone = useRef<HTMLTextAreaElement>(null);
  const prenom = p.nom.replace(/^(dr\.?|pr\.?)\s+/i, "").split(" ")[0];

  useEffect(() => { zone.current?.focus(); }, []);

  const envoyer = () => {
    if (texte.trim() && !p.occupe) p.onTexte(texte.trim());
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="scroll min-h-0 flex-1 overflow-y-auto px-8 pb-40 pt-[10vh]">
        <div className="enter mx-auto max-w-[760px]">
          <p className="label">Nouveau projet</p>
          <h1 className="titre-serif mt-3 text-[44px] leading-[1.1]">{salutation()}{prenom ? ` ${prenom}` : ""}.<br />Que souhaitez-vous dicter ?</h1>

          <div className="carte carte-saisie mt-10 p-1.5">
            <label htmlFor="dictee-texte" className="sr-only-v3">Texte de la dictée</label>
            <textarea
              id="dictee-texte" ref={zone} value={texte} onChange={(e) => setTexte(e.target.value)} rows={6}
              onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); envoyer(); } }}
              placeholder="Collez ou tapez la dictée. Ou maintenez la touche Espace et parlez."
              className="block w-full resize-none rounded-xl bg-transparent px-4 py-3.5 text-[15.5px] leading-[1.6] placeholder:text-[var(--faint)] focus:outline-none"
            />
            <div className="flex items-center justify-between px-3 pb-2 pt-1">
              <span className="text-[12px] text-[var(--faint)]">{texte.trim() ? `${texte.trim().split(/\s+/).length} mots` : "Rien n'est conservé sur nos serveurs."}</span>
              <button type="button" className="btn btn-primary btn-sm" disabled={!texte.trim() || p.occupe} onClick={envoyer}>
                Préparer le projet <span className="kbd">{estMac() ? "⌘↵" : "Ctrl+↵"}</span>
              </button>
            </div>
          </div>

          <div className="mt-12">
            <p className="label">Exemples de dictée</p>
            <ul className="mt-3 grid gap-3 sm:grid-cols-3">
              {dicteesExemples.map((ex) => (
                <li key={ex.titre}>
                  <button type="button" onClick={() => { setTexte(ex.texte); zone.current?.focus(); }}
                    className="carte h-full w-full px-5 py-[18px] text-left transition-colors hover:border-[#BDB8AC]">
                    <span className="text-[11.5px] text-[var(--faint)]">{ex.organe}</span>
                    <span className="mt-1 block text-[14px] font-medium">{ex.titre}</span>
                    <span className="mt-2 line-clamp-3 text-[12.5px] leading-[1.5] text-[var(--mute)]">{ex.texte}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
      <BarreDictee etat={p.etatMicro} secondes={p.secondes} occupe={p.occupe} onBasculer={p.onBasculerMicro} onAnnuler={p.onAnnulerMicro} />
    </div>
  );
}
