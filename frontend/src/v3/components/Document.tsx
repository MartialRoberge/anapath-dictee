// Le projet de compte rendu comme document éditable directement dans le texte.
import { useRef } from "react";
import { ordreDocument, titreAffiche, trouSuivant, type ProjetLocal } from "../lib/session";
import { aRelire } from "../lib/pourquoi";
import type { Element } from "../types";
import { focaliserTrou } from "../lib/format";
import LigneElement from "./LigneElement";

interface Props {
  local: ProjetLocal;
  selection: string | null;
  surlignes: string[];
  onSelect: (id: string | null) => void;
  onTitre: (t: string) => void;
  onEdit: (el: Element, avant: string, apres: string, modifies: number) => void;
  onRemplir: (el: Element, v: string) => void;
  onIgnorer: (el: Element) => void;
  onRouvrir: (el: Element) => void;
}

export default function Document(p: Props) {
  const { local } = p;
  const titreRef = useRef<HTMLHeadingElement>(null);
  const titre = titreAffiche(local);
  const legende = local.projet.elements.some(aRelire);

  const naviguer = (depuis: string | null, sens: 1 | -1): boolean => {
    const id = trouSuivant(local, depuis, sens);
    if (!id) return false;
    focaliserTrou(id);
    p.onSelect(id);
    return true;
  };

  // Tab / Maj+Tab : trou suivant / précédent ; s'il n'y en a plus, le comportement natif reprend.
  const clavier = (e: React.KeyboardEvent) => {
    if (e.key !== "Tab") return;
    const cible = e.target as HTMLElement;
    const depuis = cible.closest<HTMLElement>("[data-eid]")?.dataset.eid ?? null;
    // Dans une fenêtre de saisie de trou, la touche est gérée par le trou lui-même.
    if (cible.closest(".pop")) return;
    if (naviguer(depuis, e.shiftKey ? -1 : 1)) e.preventDefault();
  };

  return (
    <article className="doc" onKeyDown={clavier} aria-label="Projet de compte rendu">
      <h1
        key={titre} ref={titreRef} className="titre-serif text-[28px] leading-[1.2] outline-none max-sm:text-[22px] [overflow-wrap:anywhere]" contentEditable suppressContentEditableWarning spellCheck={false}
        role="textbox" aria-label="Titre du compte rendu"
        onBlur={() => {
          const t = (titreRef.current?.innerText ?? "").replace(/\s+/g, " ").trim();
          if (t && t !== titre) p.onTitre(t);
          else if (titreRef.current) titreRef.current.innerText = titre;
        }}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.currentTarget.blur(); } }}
      >{titre}</h1>
      <p className="mt-2 text-[13px] text-[var(--faint)]">
        Projet à relire · {local.projet.contexte.organes_libelles.join(", ") || "organe non identifié"}
        {local.projet.contexte.prelevement ? ` · ${local.projet.contexte.prelevement}` : ""}
      </p>

      {legende && (
        <p className="legende mt-3" aria-label="Légende">
          <span><span className="puce-bas">Soulignement ambre</span> : phrase à relire</span>
        </p>
      )}

      <div className="mt-8 space-y-9">
        {ordreDocument(local.projet).map(({ section, elements }) => (
          <section key={section.id} aria-labelledby={`sec-${section.id}`}>
            <h2 id={`sec-${section.id}`} className="section-titre mb-2.5">{section.titre}</h2>
            <div className="space-y-0.5">
              {elements.map((el) => (
                <LigneElement
                  key={el.id} el={el} local={local} selectionne={p.selection === el.id} surligne={p.surlignes.includes(el.id)}
                  onSelect={p.onSelect} onEdit={p.onEdit} onRemplir={p.onRemplir} onIgnorer={p.onIgnorer} onRouvrir={p.onRouvrir}
                  onNavigueTrou={(id, sens) => naviguer(id, sens)}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
      <p className="mt-12 border-t border-[var(--line)] pt-4 text-[12px] leading-relaxed text-[var(--faint)]">
        Projet généré par MARC, outil d'aide à la rédaction. Le praticien relit, corrige et valide seul le compte rendu.
      </p>
    </article>
  );
}
