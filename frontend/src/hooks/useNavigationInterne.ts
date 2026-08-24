/**
 * Le retour arriere du navigateur reste DANS MARC.
 *
 * L'application n'a pas de routeur : « Atelier », « Historique » et
 * « Administration » sont des etats React, et l'URL ne bouge jamais. Le premier
 * retour arriere sortait donc du site, en pleine redaction — et le compte rendu
 * en cours n'etait plus a l'ecran. C'est la pire chose qu'un outil de redaction
 * puisse faire.
 *
 * On empile donc une entree d'historique par page visitee, et on ecoute le
 * retour. Le geste devient ce que le praticien attend : revenir a la page
 * precedente de MARC.
 */

import { useEffect, useRef } from "react";

export function useNavigationInterne<T extends string>(
  page: T,
  aller: (page: T) => void,
): void {
  const courante = useRef<T>(page);

  // Une entree d'ancrage, posee une seule fois : sans elle, le tout premier
  // retour arriere quitterait encore le site puisqu'il n'y aurait rien
  // derriere la page courante.
  useEffect(() => {
    window.history.replaceState({ marc: courante.current }, "");
  }, []);

  useEffect(() => {
    if (page === courante.current) return;
    courante.current = page;
    window.history.pushState({ marc: page }, "");
  }, [page]);

  useEffect(() => {
    function auRetour(evenement: PopStateEvent) {
      const cible = (evenement.state as { marc?: T } | null)?.marc;
      // Sans etat MARC, on est revenu avant l'entree d'ancrage. On se replace
      // sur l'atelier plutot que de laisser le navigateur sortir : perdre le
      // compte rendu en cours d'un geste reflexe est inacceptable.
      const destination = cible ?? courante.current;
      courante.current = destination;
      aller(destination);
      if (cible === undefined) {
        window.history.replaceState({ marc: destination }, "");
      }
    }
    window.addEventListener("popstate", auRetour);
    return () => window.removeEventListener("popstate", auRetour);
  }, [aller]);
}
