// Historique LOCAL : IndexedDB (repli mémoire si indisponible). Rien n'est envoyé au serveur.
// Aucun chiffrement (non requis) mais purge totale possible depuis la barre latérale.
import type { ProjetLocal } from "./session";

export interface Recent { id: string; titre: string; maj: number; organes: string; alertes: number; trous: number }

const DB = "marc_v3";
const STORE = "projets";
const memoire = new Map<string, ProjetLocal>();

function ouvrir(): Promise<IDBDatabase | null> {
  return new Promise((resolve) => {
    try {
      if (typeof indexedDB === "undefined") return resolve(null);
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "projet.id" });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

const promesse = <T,>(r: IDBRequest<T>) =>
  new Promise<T>((res, rej) => {
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });

export function resume(l: ProjetLocal): Recent {
  const ouverts = l.projet.elements.filter((e) => e.type === "trou" && e.statut === "a_completer" && !(e.id in l.fills)).length;
  return {
    id: l.projet.id,
    titre: l.projet.titre,
    maj: l.maj,
    organes: l.projet.contexte.organes_libelles.join(", "),
    alertes: l.projet.alertes.filter((a) => !l.alertes[a.id]).length,
    trous: ouverts,
  };
}

export async function sauvegarder(l: ProjetLocal): Promise<void> {
  memoire.set(l.projet.id, l);
  const db = await ouvrir();
  if (!db) return;
  try {
    await promesse(db.transaction(STORE, "readwrite").objectStore(STORE).put(JSON.parse(JSON.stringify(l))));
  } catch {
    /* le repli mémoire suffit */
  } finally {
    db.close();
  }
}

export async function lister(): Promise<Recent[]> {
  const db = await ouvrir();
  let tous: ProjetLocal[] = [...memoire.values()];
  if (db) {
    try {
      tous = await promesse(db.transaction(STORE).objectStore(STORE).getAll() as IDBRequest<ProjetLocal[]>);
    } catch {
      /* repli */
    } finally {
      db.close();
    }
  }
  return tous.map(resume).sort((a, b) => b.maj - a.maj);
}

export async function charger(id: string): Promise<ProjetLocal | null> {
  const db = await ouvrir();
  if (!db) return memoire.get(id) ?? null;
  try {
    return ((await promesse(db.transaction(STORE).objectStore(STORE).get(id))) as ProjetLocal | undefined) ?? memoire.get(id) ?? null;
  } catch {
    return memoire.get(id) ?? null;
  } finally {
    db.close();
  }
}

export async function supprimer(id: string): Promise<void> {
  memoire.delete(id);
  const db = await ouvrir();
  if (!db) return;
  try {
    await promesse(db.transaction(STORE, "readwrite").objectStore(STORE).delete(id));
  } catch {
    /* ignoré */
  } finally {
    db.close();
  }
}

/** Purge complète de l'historique local. */
export async function purger(): Promise<void> {
  memoire.clear();
  const db = await ouvrir();
  if (!db) return;
  try {
    await promesse(db.transaction(STORE, "readwrite").objectStore(STORE).clear());
  } catch {
    /* ignoré */
  } finally {
    db.close();
  }
}
