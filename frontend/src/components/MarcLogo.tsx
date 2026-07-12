/**
 * Logo MARC — Module d'Assistance à la Rédaction des Comptes-rendus.
 * Une solution Gilbert : badge médical vert clinique + accent bleu Gilbert.
 * Motif : un compte-rendu (document) souligné d'une ligne de vie (pouls).
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
        <linearGradient id="marc-grad" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0" stopColor="#14b8a6" />
          <stop offset="1" stopColor="#0d9488" />
        </linearGradient>
      </defs>
      {/* Badge arrondi */}
      <rect x="2" y="2" width="28" height="28" rx="8" fill="url(#marc-grad)" />
      {/* Document (compte-rendu) */}
      <path
        d="M11 8.5h7.5L22 12v11a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 10 23V10a1.5 1.5 0 0 1 1-1.5Z"
        fill="#ffffff"
        opacity="0.96"
      />
      {/* Ligne de vie / pouls */}
      <path
        d="M12.5 19.5h1.7l1-2.2 1.4 3.2 1-1.5h1.9"
        stroke="#0d9488"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Lignes de texte */}
      <path d="M12.6 13h5.2M12.6 15.2h3.6" stroke="#0d9488" strokeWidth="1.1" strokeLinecap="round" opacity="0.55" />
      {/* Accent bleu Gilbert */}
      <circle cx="24" cy="9" r="3" fill="#2140e8" stroke="#ffffff" strokeWidth="1.4" />
    </svg>
  );
}

export function MarcWordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`font-heading font-extrabold tracking-tight ${className}`}>
      <span className="text-iris-600 dark:text-iris-400">MAR</span>
      <span className="text-gilbert-500">C</span>
    </span>
  );
}
