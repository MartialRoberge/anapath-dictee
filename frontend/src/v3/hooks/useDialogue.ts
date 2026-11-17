// Dialogue accessible : focus placé à l'ouverture, piégé dans le dialogue (Tab / Maj+Tab), rendu à l'élément d'origine à la fermeture ; Échap ferme.
import { useEffect, useRef, type RefObject } from "react";

const FOCALISABLES = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useDialogue(racine: RefObject<HTMLElement | null>, onFermer: () => void, options: { focusInitial?: boolean; rendreFocus?: boolean } = {}) {
  const { focusInitial = true, rendreFocus = true } = options;
  const fermer = useRef(onFermer);
  fermer.current = onFermer;
  useEffect(() => {
    const el = racine.current;
    if (!el) return;
    const origine = document.activeElement as HTMLElement | null;
    if (focusInitial) (el.querySelector<HTMLElement>("[autofocus], textarea, input") ?? el.querySelector<HTMLElement>(FOCALISABLES))?.focus();
    const touche = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fermer.current(); return; }
      if (e.key !== "Tab") return;
      const l = [...el.querySelectorAll<HTMLElement>(FOCALISABLES)].filter((x) => x.offsetParent !== null || x === document.activeElement);
      if (!l.length) { e.preventDefault(); return; }
      const premier = l[0], dernier = l[l.length - 1];
      if (!el.contains(document.activeElement)) { e.preventDefault(); premier.focus(); }
      else if (e.shiftKey && document.activeElement === premier) { e.preventDefault(); dernier.focus(); }
      else if (!e.shiftKey && document.activeElement === dernier) { e.preventDefault(); premier.focus(); }
    };
    document.addEventListener("keydown", touche, true);
    return () => {
      document.removeEventListener("keydown", touche, true);
      if (rendreFocus && origine && document.contains(origine)) origine.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
