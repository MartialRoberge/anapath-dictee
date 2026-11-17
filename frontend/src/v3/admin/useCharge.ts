// Chargement asynchrone d'une section : données, erreur, rechargement. Annule la mise à jour d'une réponse périmée.
import { useCallback, useEffect, useState } from "react";

export function useCharge<T>(charger: () => Promise<T>, cles: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let actif = true;
    charger()
      .then((d) => { if (actif) { setData(d); setErreur(null); } })
      .catch((e: unknown) => { if (actif) setErreur(e instanceof Error ? e.message : "Chargement impossible."); });
    return () => { actif = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...cles, version]);
  const recharger = useCallback(() => setVersion((v) => v + 1), []);
  return { data, setData, erreur, recharger };
}
