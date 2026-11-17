// Carte blanche : libelle, grand chiffre, variation vs période précédente.
interface Props {
  label: string;
  valeur: string;
  variation?: number | null;
  /** true si une hausse est une bonne nouvelle (defaut) ; false pour les durees. */
  hausseBonne?: boolean;
  note?: string;
}

export function KpiCard({ label, valeur, variation, hausseBonne = true, note }: Props) {
  const bon = variation == null ? null : (variation >= 0) === hausseBonne;
  return (
    <div className="adm-carte adm-entree">
      <div className="adm-label">{label}</div>
      <div className="adm-serif mt-3 text-[44px] leading-none tabular-nums">{valeur}</div>
      <div className="mt-3 flex items-center gap-2 text-[12px]" style={{ color: "var(--adm-doux)" }}>
        {variation != null && (
          <span className="whitespace-nowrap tabular-nums" style={{ color: bon ? "var(--adm-accent)" : "var(--adm-encre)" }}>
            {variation >= 0 ? "+" : ""}{Math.round(variation * 100)} %
          </span>
        )}
        <span>{note ?? (variation != null ? "vs période précédente" : "")}</span>
      </div>
    </div>
  );
}
