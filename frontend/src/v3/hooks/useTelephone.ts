// Détection « téléphone » (portrait ou paysage) et suivi du clavier virtuel via visualViewport.
import { useEffect, useSyncExternalStore } from "react";
import { estChampSaisie } from "../lib/raccourcis";

/** Même requête que dans v3.css : écran étroit, ou paysage bas d'un téléphone. */
export const REQ_TELEPHONE = "(max-width: 639px), (max-height: 500px) and (max-width: 940px)";

const abonner = (q: string) => (cb: () => void) => {
  const m = window.matchMedia(q);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
};

export function useMedia(q: string): boolean {
  return useSyncExternalStore(
    typeof window === "undefined" ? () => () => {} : abonner(q),
    () => (typeof window === "undefined" ? false : window.matchMedia(q).matches),
    () => false,
  );
}

export const useTelephone = () => useMedia(REQ_TELEPHONE);

/**
 * Clavier virtuel : quand il masque une partie de l'écran, la coque et les feuilles prennent la hauteur visible
 * (variables --vvh et --vvtf lues par v3.css) et le champ actif reste visible.
 */
export function useClavierVirtuel() {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const racine = document.documentElement;
    const maj = () => {
      const ouvert = vv.scale <= 1.01 && window.innerHeight - vv.height > 120;
      if (ouvert) {
        racine.style.setProperty("--vvh", `${Math.round(vv.height)}px`);
        if (vv.offsetTop > 0) racine.style.setProperty("--vvtf", `translateY(${Math.round(vv.offsetTop)}px)`);
        else racine.style.removeProperty("--vvtf");
      } else {
        racine.style.removeProperty("--vvh");
        racine.style.removeProperty("--vvtf");
      }
    };
    const focus = (e: FocusEvent) => {
      const t = e.target;
      if (!estChampSaisie(t)) return;
      window.setTimeout(() => {
        if (racine.style.getPropertyValue("--vvh")) (t as HTMLElement).scrollIntoView({ block: "nearest", behavior: "smooth" });
      }, 350);
    };
    vv.addEventListener("resize", maj);
    vv.addEventListener("scroll", maj);
    document.addEventListener("focusin", focus);
    maj();
    return () => {
      vv.removeEventListener("resize", maj);
      vv.removeEventListener("scroll", maj);
      document.removeEventListener("focusin", focus);
      racine.style.removeProperty("--vvh");
      racine.style.removeProperty("--vvtf");
    };
  }, []);
}
