// Une ligne du projet : texte éditable au clic (sans crayon). Un trou affiche son champ inline.
import { useRef } from "react";
import { libelleSansUnite } from "../lib/holes";
import { aRelire } from "../lib/pourquoi";
import { caracteresModifies, estTrou, etatTrou, texteElement, type ProjetLocal } from "../lib/session";
import type { Element } from "../types";
import Trou from "./Trou";

// « plaintext-only » : pas de HTML collé ; repli sur « true » + collage nettoyé ailleurs.
const EDITABLE: "plaintext-only" | "true" = (() => {
  try {
    const d = document.createElement("div");
    d.contentEditable = "plaintext-only";
    return d.contentEditable === "plaintext-only" ? "plaintext-only" : "true";
  } catch {
    return "true";
  }
})();

interface Props {
  el: Element;
  local: ProjetLocal;
  selectionne: boolean;
  surligne: boolean;
  onSelect: (id: string) => void;
  onEdit: (el: Element, avant: string, apres: string, modifies: number) => void;
  onRemplir: (el: Element, v: string) => void;
  onIgnorer: (el: Element) => void;
  onRouvrir: (el: Element) => void;
  onNavigueTrou: (id: string, sens: 1 | -1) => void;
}

export default function LigneElement(p: Props) {
  const { el, local } = p;
  const ref = useRef<HTMLSpanElement>(null);
  const texte = texteElement(local, el);
  const trou = estTrou(el);

  const commit = () => {
    const n = ref.current;
    if (!n) return;
    const nouveau = (n.innerText ?? "").replace(/\s*\n+\s*/g, " ").trim();
    if (nouveau === texte) return;
    if (!nouveau) { n.innerText = texte; return; } // un élément vidé revient à son texte, jamais de ligne fantôme
    p.onEdit(el, texte, nouveau, caracteresModifies(texte, nouveau));
  };

  const touche = (e: React.KeyboardEvent<HTMLSpanElement>) => {
    if (e.key === "Enter") { e.preventDefault(); e.currentTarget.blur(); }
    else if (e.key === "Escape") { if (ref.current) ref.current.innerText = texte; e.currentTarget.blur(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const s = window.getSelection();
      const len = (ref.current?.innerText ?? "").length;
      const bas = e.key === "ArrowDown";
      if (s && s.isCollapsed && (bas ? s.anchorOffset >= len : s.anchorOffset === 0)) {
        e.preventDefault();
        const tous = Array.from(document.querySelectorAll<HTMLElement>("[data-nav]"));
        const i = tous.indexOf(e.currentTarget);
        tous[i + (bas ? 1 : -1)]?.focus();
      }
    }
  };

  const collage = (e: React.ClipboardEvent) => {
    e.preventDefault();
    document.execCommand("insertText", false, e.clipboardData.getData("text/plain").replace(/\s*\n+\s*/g, " "));
  };

  const relire = !trou && aRelire(el); // un trou n'a pas de confiance à afficher : sa marque est le champ lui-même

  return (
    <div
      className="el" data-eid={el.id} data-relire={relire} data-selected={p.selectionne} data-surligne={p.surligne}
      onClick={() => p.onSelect(el.id)}
    >
      {relire && <span className="sr-only-v3">À relire. </span>}
      {trou ? (
        <span className="text-[15px]">
          <span className="mr-2 text-[var(--mute)]">{libelleSansUnite(el.texte)} :</span>
          <Trou
            el={el} etat={etatTrou(local, el)} valeur={local.fills[el.id] ?? ""}
            onRemplir={(v) => p.onRemplir(el, v)} onIgnorer={() => p.onIgnorer(el)} onRouvrir={() => p.onRouvrir(el)}
            onNavigue={(sens) => p.onNavigueTrou(el.id, sens)}
          />
        </span>
      ) : (
        <>
          {el.type === "liste" && <span aria-hidden className="mr-2 text-[var(--faint)]">–</span>}
          <span
            key={texte} ref={ref} data-nav className={`el-texte ${el.type === "titre" ? "!font-semibold !text-[var(--ink)]" : ""}`}
            contentEditable={EDITABLE} suppressContentEditableWarning spellCheck lang="fr" role="textbox" aria-multiline="false"
            aria-label={el.type === "titre" ? "Titre de sous-partie" : "Texte du compte rendu"}
            onFocus={() => p.onSelect(el.id)} onBlur={commit} onKeyDown={touche} onPaste={collage}
          >
            {texte}
          </span>
        </>
      )}
    </div>
  );
}
