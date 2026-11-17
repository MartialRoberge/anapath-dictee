// Niveau de service N1-N3 expliqué sobrement (N0 = nominal, rien à afficher).
import type { Contexte } from "../types";

const TEXTES: Record<Exclude<Contexte["niveau_service"], "N0">, { titre: string; texte: string }> = {
  N1: { titre: "Service partiel", texte: "Une partie des références manque (par exemple un code ou un exemple de style). Le projet est complet, certains codes sont partiels ou absents." },
  N2: { titre: "Gabarit générique", texte: "Cet organe n'a pas encore de gabarit dédié. Le projet suit la structure commune ; les champs attendus restent à compléter." },
  N3: { titre: "Mode minimal", texte: "Aucune référence exploitable : la dictée est seulement mise en forme, sans exigences ni codes. Relisez-la intégralement." },
};

export default function BandeauService({ niveau }: { niveau: Contexte["niveau_service"] }) {
  if (niveau === "N0") return null;
  const t = TEXTES[niveau];
  return (
    <div role="status" className="enter mb-8 flex gap-3 rounded-xl border border-[#E8D3A8] bg-[var(--amber-soft)] px-4 py-3 text-[13px] leading-relaxed">
      <span className="num mt-0.5 flex-none text-[11.5px] font-semibold text-[var(--amber)]">{niveau}</span>
      <p><b className="font-semibold">{t.titre}.</b> {t.texte}</p>
    </div>
  );
}
