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

  // Le champ n'est pas focalisé à l'arrivée : l'Espace maintenu doit pouvoir lancer la dictée (c'est le geste principal).
  // Coller (Ctrl/Cmd+V) ou taper un caractère depuis n'importe où bascule vers le champ de texte.
  useEffect(() => {
    const libre = (t: EventTarget | null) => !(t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)));
    const coller = (e: ClipboardEvent) => {
      const t = e.clipboardData?.getData("text") ?? "";
      if (!t || !libre(e.target)) return;
      e.preventDefault();
      setTexte((x) => (x ? `${x}\n${t}` : t));
      zone.current?.focus();
    };
    const taper = (e: KeyboardEvent) => {
      if (e.key.length !== 1 || e.key === " " || e.metaKey || e.ctrlKey || e.altKey || !libre(e.target) || (e.target as HTMLElement).tagName === "BUTTON") return;
      zone.current?.focus();
    };
    document.addEventListener("paste", coller);
    document.addEventListener("keydown", taper);
    return () => { document.removeEventListener("paste", coller); document.removeEventListener("keydown", taper); };
  }, []);

  const envoyer = () => {
    if (texte.trim() && !p.occupe) p.onTexte(texte.trim());
  };
  const mots = texte.trim() ? texte.trim().split(/\s+/).length : 0;

  // Tient dans 1280 x 800 sans défiler : titre, une carte de saisie (texte + dictée), trois exemples compacts.
  return (
    <div className="scroll flex min-h-0 flex-1 flex-col overflow-y-auto px-8 py-6">
      <div className="enter mx-auto my-auto w-full max-w-[720px]">
        <p className="label">Nouveau projet</p>
        <h1 className="titre-serif mt-2 text-[clamp(28px,4.6vh,40px)] leading-[1.15]">{salutation()}{prenom ? ` ${prenom}` : ""}.<br />Que souhaitez-vous dicter ?</h1>

        <div className="carte carte-saisie mt-6 p-2">
          <label htmlFor="dictee-texte" className="sr-only-v3">Texte de la dictée</label>
          <textarea
            id="dictee-texte" ref={zone} value={texte} onChange={(e) => setTexte(e.target.value)} rows={5}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); envoyer(); }
              else if (e.key === "Escape") e.currentTarget.blur();
            }}
            placeholder="Collez ou tapez la dictée."
            className="block w-full resize-none rounded-lg bg-transparent px-3 py-2.5 text-[16px] leading-[1.5] placeholder:text-[var(--faint)] focus:outline-none"
          />
          <div className="flex flex-wrap items-center gap-3 border-t border-[var(--line-soft)] px-1 pb-0.5 pt-2.5">
            <BarreDictee etat={p.etatMicro} secondes={p.secondes} occupe={p.occupe} onBasculer={p.onBasculerMicro} onAnnuler={p.onAnnulerMicro} />
            <button type="button" className="btn btn-primary" disabled={!texte.trim() || p.occupe} onClick={envoyer}>
              Préparer le projet <span className="kbd">{estMac() ? "⌘↵" : "Ctrl+↵"}</span>
            </button>
          </div>
        </div>
        <p className="num mt-2 px-1 text-[12px] text-[var(--faint)]">{mots > 0 ? `${mots} mots · ` : ""}Rien n'est conservé sur nos serveurs. Échap quitte le champ.</p>

        <div className="mt-6">
          <p className="label">Exemples de dictée</p>
          <ul className="mt-2 grid gap-3 sm:grid-cols-3">
            {dicteesExemples.map((ex) => (
              <li key={ex.titre}>
                <button type="button" onClick={() => { setTexte(ex.texte); zone.current?.focus(); }}
                  className="carte h-full w-full px-4 py-3 text-left transition-[background] hover:bg-[var(--select)]">
                  <span className="text-[12px] text-[var(--faint)]">{ex.organe}</span>
                  <span className="mt-0.5 block text-[15px] font-medium">{ex.titre}</span>
                  <span className="mt-1 line-clamp-2 text-[13px] leading-[1.4] text-[var(--mute)]">{ex.texte}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
