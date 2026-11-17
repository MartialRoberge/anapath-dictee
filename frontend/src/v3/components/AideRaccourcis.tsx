// Aide des raccourcis : fenêtre modale (focus piégé, Échap ferme). Texte seul, aucune icône.
import { useEffect, useRef } from "react";
import { groupes } from "../lib/raccourcis";

export default function AideRaccourcis({ onFermer }: { onFermer: () => void }) {
  const fermer = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const avant = document.activeElement as HTMLElement | null;
    fermer.current?.focus();
    return () => avant?.focus?.();
  }, []);
  const clavier = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onFermer(); return; }
    if (e.key === "Tab") { e.preventDefault(); fermer.current?.focus(); } // une seule cible : le focus reste dans la fenêtre
  };
  return (
    <div className="modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onFermer(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="titre-aide" onKeyDown={clavier} className="aide p-7 max-sm:p-5">
        <div className="flex items-baseline gap-4">
          <h2 id="titre-aide" className="titre-serif flex-1 text-[22px] leading-tight">Raccourcis clavier</h2>
          <button ref={fermer} type="button" className="btn btn-sm" onClick={onFermer}>Fermer <span className="kbd">Échap</span></button>
        </div>
        <p className="mt-2 text-[13px] text-[var(--mute)]">Le parcours complet se fait sans souris : dicter, combler les trous, traiter les points à vérifier, valider, copier.</p>
        <div className="mt-6 grid gap-x-10 gap-y-6 sm:grid-cols-2">
          {groupes().map((g) => (
            <section key={g.titre} aria-label={g.titre}>
              <h3 className="label mb-2">{g.titre}</h3>
              <dl className="space-y-2">
                {g.items.map((r) => (
                  <div key={r.touches + r.action} className="flex items-baseline gap-3 text-[13px]">
                    <dt className="w-[132px] flex-none"><span className="kbd">{r.touches}</span></dt>
                    <dd className="leading-snug text-[var(--mute)]">{r.action}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
        <p className="mt-7 border-t border-[var(--line)] pt-4 text-[12px] leading-relaxed text-[var(--faint)]">
          Une pédale programmée sur Espace ou sur une de ces combinaisons fonctionne comme le clavier. Les raccourcis Alt utilisent la position physique de la touche.
        </p>
      </div>
    </div>
  );
}
