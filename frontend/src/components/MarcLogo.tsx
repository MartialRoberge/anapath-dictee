/**
 * Logo MARC — Module d'Assistance à la Rédaction des Comptes-rendus.
 * Une solution Gilbert. Badge dégradé bleu #1E43E5 → vert #0A7C5A (charte Lexia),
 * motif compte-rendu souligné d'une ligne de vie.
 */

interface MarcLogoProps {
  size?: number;
  className?: string;
}

export function MarcLogo({ size = 28, className = "" }: MarcLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="marc-grad" x1="2" y1="2" x2="30" y2="30">
          <stop offset="0" stopColor="#1E43E5" />
          <stop offset="1" stopColor="#0A7C5A" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="28" height="28" rx="9" fill="url(#marc-grad)" />
      {/* Document (compte-rendu) */}
      <path
        d="M11 8.5h7.5L22 12v11a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 10 23V10a1.5 1.5 0 0 1 1-1.5Z"
        fill="#ffffff"
        opacity="0.97"
      />
      {/* Ligne de vie / pouls */}
      <path
        d="M12.4 19.6h1.7l1-2.3 1.5 3.4 1-1.6h1.9"
        stroke="#1E43E5"
        strokeWidth="1.35"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <path d="M12.5 13h5.4M12.5 15.3h3.7" stroke="#1E43E5" strokeWidth="1.1" strokeLinecap="round" opacity="0.5" />
    </svg>
  );
}

export function MarcWordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`font-heading font-extrabold tracking-tight text-foreground ${className}`}
    >
      MARC
    </span>
  );
}
