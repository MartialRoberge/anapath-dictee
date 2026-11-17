// Barre latérale sombre : nouveau projet, récents (historique local), administration, compte.
import { useState } from "react";
import type { Recent } from "../lib/history";
import { touche } from "../lib/raccourcis";

interface Props {
  recents: Recent[];
  courantId: string | null;
  vue: "nouveau" | "projet" | "admin";
  nom: string;
  admin: boolean;
  demo: boolean;
  onNouveau: () => void;
  onOuvrir: (id: string) => void;
  onSupprimer: (id: string) => void;
  onPurger: () => void;
  onAdmin: () => void;
  onAide: () => void;
  onDeconnexion: () => void;
}

const jour = (t: number) => {
  const d = new Date(t);
  const auj = new Date();
  const hier = new Date(auj.getTime() - 864e5);
  if (d.toDateString() === auj.toDateString()) return "Aujourd'hui";
  if (d.toDateString() === hier.toDateString()) return "Hier";
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
};

export default function Sidebar(p: Props) {
  const [confirmer, setConfirmer] = useState(false);
  const groupes: Array<[string, Recent[]]> = [];
  for (const r of p.recents) {
    const j = jour(r.maj);
    const g = groupes.find(([k]) => k === j);
    if (g) g[1].push(r);
    else groupes.push([j, [r]]);
  }

  return (
    <aside className="side flex h-full min-h-0 flex-col" aria-label="Navigation">
      <div className="px-5 pb-4 pt-6">
        <p className="text-[17px] font-semibold tracking-[0.12em]">MARC</p>
        <p className="side-mute mt-0.5 text-[12px]">Une solution Gilbert</p>
      </div>
      <div className="px-3">
        <button type="button" onClick={p.onNouveau} aria-current={p.vue === "nouveau"} className="side-item font-medium shadow-[inset_0_0_0_1px_var(--side-line)]">
          <span className="flex-1">Nouveau projet</span><span className="kbd !bg-transparent !text-[var(--side-mute)]">{touche("N")}</span>
        </button>
      </div>

      <nav className="scroll mt-6 min-h-0 flex-1 overflow-y-auto px-3" aria-label="Projets récents">
        <p className="side-mute px-2.5 pb-1.5 text-[12px] font-medium uppercase tracking-[0.1em]">Récents</p>
        {p.recents.length === 0 && <p className="side-mute px-2.5 text-[13px] leading-relaxed">Aucun projet. L'historique reste sur cet appareil.</p>}
        {groupes.map(([j, liste]) => (
          <div key={j} className="mb-3">
            <p className="side-mute px-2.5 py-1 text-[12px]">{j}</p>
            <ul>
              {liste.map((r) => (
                <li key={r.id} className="group relative">
                  <button type="button" onClick={() => p.onOuvrir(r.id)} aria-current={p.vue === "projet" && p.courantId === r.id} className="side-item flex-col !items-start !gap-0.5">
                    <span className="w-full truncate pr-1 text-[13px]">{r.organes || "Projet"} <span className="side-mute">· {new Date(r.maj).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</span></span>
                    <span className="side-mute w-full truncate text-[12px]">
                      {r.trous > 0 ? `${r.trous} à compléter` : "Complet"}{r.alertes > 0 ? ` · ${r.alertes} à vérifier` : ""}
                    </span>
                  </button>
                  <button type="button" onClick={() => p.onSupprimer(r.id)} aria-label={`Supprimer le projet ${r.organes || ""} de l'historique local`}
                    className="side-mute absolute right-2 top-2.5 hidden h-8 items-center rounded-md bg-[var(--side-hover)] px-2 text-[12px] [@media(hover:none)]:flex hover:bg-[var(--side-line)] hover:text-[var(--side-text)] focus-visible:flex group-hover:flex">Retirer</button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="side-pied border-t border-[var(--side-line)] px-3 py-2">
        <button type="button" onClick={p.onAide} className="side-item side-mute"><span className="flex-1">Raccourcis clavier</span><span className="kbd !bg-transparent !text-[var(--side-mute)]">?</span></button>
        {p.admin && (
          <button type="button" onClick={p.onAdmin} aria-current={p.vue === "admin"} className="side-item">Administration</button>
        )}
        {p.recents.length > 0 && (confirmer ? (
          <div className="px-2.5 py-1.5 text-[12px]" role="alertdialog" aria-label="Confirmer la purge">
            <p className="side-mute">Supprimer tout l'historique de cet appareil ?</p>
            <div className="mt-1.5 flex gap-3">
              <button type="button" className="font-medium underline underline-offset-2" onClick={() => { p.onPurger(); setConfirmer(false); }}>Supprimer</button>
              <button type="button" className="side-mute hover:text-[var(--side-text)]" onClick={() => setConfirmer(false)}>Annuler</button>
            </div>
          </div>
        ) : (
          <button type="button" onClick={() => setConfirmer(true)} className="side-item side-mute">Purger l'historique local</button>
        ))}
        <div className="mt-1 flex items-center gap-2 px-2.5 py-2">
          <span className="min-w-0 flex-1 truncate text-[13px]">{p.nom}{p.demo && <span className="side-mute"> · démo</span>}</span>
          {!p.demo && <button type="button" onClick={p.onDeconnexion} className="side-mute rounded-md px-2 py-1.5 text-[13px] hover:bg-[var(--side-hover)] hover:text-[var(--side-text)]">Déconnexion</button>}
        </div>
      </div>
    </aside>
  );
}
