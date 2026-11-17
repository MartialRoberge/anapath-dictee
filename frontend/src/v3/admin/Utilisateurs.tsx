// Utilisateurs : tous les comptes, triés par dernière activité, avec compteurs par origine et habilitation de valideur (conformité).
import { useState } from "react";
import { dateHeure, ilYa, nombre } from "./format";
import type { AdminApi, UtilisateurAdmin } from "./types";
import { useCharge } from "./useCharge";

/** Dernière activité la plus récente d'abord ; les comptes sans activité en fin de liste. */
export const trierParActivite = (l: UtilisateurAdmin[]): UtilisateurAdmin[] =>
  [...l].sort((a, b) => (b.derniere_activite ?? "").localeCompare(a.derniere_activite ?? "") || a.nom.localeCompare(b.nom));

export function TableUtilisateurs({ utilisateurs, onHabilitation, enCours = [] }: { utilisateurs: UtilisateurAdmin[]; onHabilitation: (u: UtilisateurAdmin, v: boolean) => void; enCours?: string[] }) {
  if (!utilisateurs.length) return <p className="adm-carte m-0 adm-doux">Aucun compte.</p>;
  return (
    <div className="adm-carte adm-defile-x !p-2">
      <table className="adm-table">
        <thead>
          <tr><th scope="col">Compte</th><th scope="col">Dernière activité</th><th scope="col" className="num">v3</th><th scope="col" className="num">Ancienne version</th><th scope="col" className="num">Étude</th><th scope="col">Valideur</th></tr>
        </thead>
        <tbody>
          {trierParActivite(utilisateurs).map((u) => (
            <tr key={u.id}>
              <td><div className="font-medium">{u.nom}{u.role === "admin" && <span className="adm-faible font-normal"> · admin</span>}</div><div className="text-[12px] adm-doux">{u.email}</div></td>
              <td title={dateHeure(u.derniere_activite)} className="whitespace-nowrap">{ilYa(u.derniere_activite)}</td>
              <td className="num">{nombre(u.projets_v3)}</td>
              <td className="num">{nombre(u.comptes_rendus_anciens)}</td>
              <td className="num">{nombre(u.dossiers_etude)}</td>
              <td>
                <button type="button" role="switch" aria-checked={u.habilite_valideur} aria-label={`Habilitation de valideur de ${u.nom}`} className="adm-bascule"
                  disabled={enCours.includes(u.id)} onClick={() => onHabilitation(u, !u.habilite_valideur)}>
                  {u.habilite_valideur ? "Habilité" : "Non habilité"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Utilisateurs({ api }: { api: AdminApi }) {
  const { data, setData, erreur } = useCharge(() => api.utilisateurs(), [api]);
  const [enCours, setEnCours] = useState<string[]>([]);
  const [alerte, setAlerte] = useState("");
  const basculer = async (u: UtilisateurAdmin, v: boolean) => {
    setAlerte(""); setEnCours((l) => [...l, u.id]);
    try {
      const r = await api.habilitation(u.id, v);
      setData((d) => d && d.map((x) => (x.id === u.id ? { ...x, habilite_valideur: r.habilite } : x)));
    } catch (e) { setAlerte((e as Error).message); }
    finally { setEnCours((l) => l.filter((i) => i !== u.id)); }
  };
  return (
    <section aria-label="Utilisateurs">
      <p className="m-0 mb-4 text-[13px] adm-doux">{data ? `${data.length} comptes, actifs ou non.` : ""} L'habilitation de valideur autorise la validation d'un compte rendu (conformité ISO 15189).</p>
      {alerte && <p role="alert" className="mb-4 text-[13px] adm-erreur">{alerte}</p>}
      {erreur && <p role="alert" className="adm-carte adm-erreur m-0">{erreur}</p>}
      {!data && !erreur && <p className="adm-doux">Chargement…</p>}
      {data && <TableUtilisateurs utilisateurs={data} onHabilitation={basculer} enCours={enCours} />}
    </section>
  );
}
