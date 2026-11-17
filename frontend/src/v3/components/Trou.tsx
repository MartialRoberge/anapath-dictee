// Trou : champ inline compact. Options en liste + saisie libre. Entrée valide et passe au trou suivant ;
// Tab valide la saisie et passe au suivant ; Maj+Tab revient en arrière ; Échap ferme.
import { useEffect, useId, useRef, useState } from "react";
import { filtrerOptions, uniteDuTrou, valeurAvecUnite, type EtatTrou } from "../lib/holes";
import { touche as libelleTouche } from "../lib/raccourcis";
import type { Element } from "../types";

const cleIgnorer = libelleTouche("I");

interface Props {
  el: Element;
  etat: EtatTrou;
  valeur: string;
  onRemplir: (v: string) => void;
  onIgnorer: () => void;
  onRouvrir: () => void;
  onNavigue: (sens: 1 | -1) => void;
}

export default function Trou({ el, etat, valeur, onRemplir, onIgnorer, onRouvrir, onNavigue }: Props) {
  const [ouvert, setOuvert] = useState(false);
  const [saisie, setSaisie] = useState("");
  const [actif, setActif] = useState(0);
  const bouton = useRef<HTMLButtonElement>(null);
  const champ = useRef<HTMLInputElement>(null);
  const racine = useRef<HTMLSpanElement>(null);
  const idListe = useId();
  const unite = uniteDuTrou(el);
  const options = filtrerOptions(el.options, saisie);
  const libre = saisie.trim() && !el.options.some((o) => o.toLowerCase() === saisie.trim().toLowerCase()) ? saisie.trim() : null;
  const items = [...options, ...(libre ? [libre] : [])];

  const ouvrir = () => { setSaisie(etat === "rempli" ? valeur : ""); setActif(0); setOuvert(true); };
  const fermer = () => { setOuvert(false); requestAnimationFrame(() => bouton.current?.focus()); };

  useEffect(() => {
    if (!ouvert) return;
    const c = champ.current;
    c?.focus();
    c?.setSelectionRange(c.value.length, c.value.length);
  }, [ouvert]);
  useEffect(() => {
    if (!ouvert) return;
    const hors = (e: MouseEvent) => { if (!racine.current?.contains(e.target as Node)) setOuvert(false); };
    document.addEventListener("mousedown", hors);
    return () => document.removeEventListener("mousedown", hors);
  }, [ouvert]);

  const valider = (v: string, sens: 1 | -1 = 1) => {
    const t = v.trim();
    if (!t) return;
    onRemplir(t);
    setOuvert(false);
    // laisse React rendre l'état « rempli » avant de déplacer le focus
    requestAnimationFrame(() => onNavigue(sens));
  };

  const ignorer = () => { onIgnorer(); setOuvert(false); requestAnimationFrame(() => onNavigue(1)); };

  const touche = (e: React.KeyboardEvent) => {
    if (e.altKey && e.code === "KeyI") { e.preventDefault(); e.stopPropagation(); ignorer(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setActif((a) => Math.min(a + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActif((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); valider(items[actif] ?? saisie); }
    else if (e.key === "Tab") {
      const v = items[actif] && saisie.trim() ? (libre && !options.length ? libre : items[actif]) : saisie;
      if (v.trim()) { e.preventDefault(); valider(v, e.shiftKey ? -1 : 1); }
      else { e.preventDefault(); setOuvert(false); requestAnimationFrame(() => onNavigue(e.shiftKey ? -1 : 1)); }
    } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fermer(); }
  };

  const affichage = etat === "rempli" ? valeurAvecUnite(valeur, unite) : etat === "ignore" ? "ignoré" : "à compléter";

  return (
    <span ref={racine} className="relative inline-block align-baseline">
      <button
        ref={bouton} type="button" data-nav data-trou={el.id} data-etat={etat} data-obligatoire={el.obligatoire}
        className="trou" aria-haspopup="listbox" aria-expanded={ouvert}
        aria-label={`${el.texte}${el.obligatoire ? " (obligatoire)" : ""} : ${affichage}`}
        onClick={() => (ouvert ? setOuvert(false) : ouvrir())}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") { e.preventDefault(); ouvrir(); }
          // Une frappe sur un trou ouvre le champ avec ce caractère : combler un trou = taper + Entrée.
          else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); setActif(0); setOuvert(true); setSaisie(e.key); }
        }}
      >
        <span>{affichage}</span>
        {el.obligatoire && etat === "ouvert" && <span className="text-[12px] font-medium text-[var(--amber)]">obligatoire</span>}
      </button>
      {ouvert && (
        <div className="pop left-0 top-full mt-1.5" onKeyDown={touche}>
          <div className="flex items-center gap-2 border-b border-[var(--line-soft)] px-2.5 pb-2 pt-1.5">
            <input
              ref={champ} value={saisie} onChange={(e) => { setSaisie(e.target.value); setActif(0); }}
              role="combobox" aria-expanded="true" aria-controls={idListe} aria-autocomplete="list" aria-label={`Valeur pour ${el.texte}`}
              placeholder={el.options.length ? "Choisir ou saisir une valeur" : "Saisir une valeur"}
              className="w-full bg-transparent text-[15px] placeholder:text-[var(--faint)] focus:outline-none"
            />
            {unite && <span className="text-[12px] text-[var(--faint)]">{unite}</span>}
          </div>
          <ul id={idListe} role="listbox" className="max-h-56 overflow-y-auto py-1">
            {items.map((o, i) => (
              <li key={o} role="presentation">
                <button type="button" role="option" aria-selected={i === actif} tabIndex={-1} className="opt" onMouseEnter={() => setActif(i)} onClick={() => valider(o)}>
                  {libre && o === libre && !el.options.includes(o) ? <>Utiliser « {o} »</> : o}
                </button>
              </li>
            ))}
            {items.length === 0 && <li className="px-3 py-2 text-[13px] text-[var(--faint)]">Saisissez une valeur puis Entrée.</li>}
          </ul>
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-[var(--line-soft)] px-2.5 pb-1 pt-2 text-[12px]">
            <span className="text-[var(--faint)]"><span className="kbd">Entrée</span> valider · <span className="kbd">Tab</span> suivant</span>
            <button type="button" tabIndex={-1} className="text-[var(--mute)] hover:text-[var(--ink)]" onClick={ignorer}>Ignorer ce champ <span className="kbd">{cleIgnorer}</span></button>
            {etat !== "ouvert" && <button type="button" tabIndex={-1} className="text-[var(--mute)] hover:text-[var(--ink)]" onClick={() => { onRouvrir(); setOuvert(false); }}>Effacer</button>}
          </div>
        </div>
      )}
    </span>
  );
}
