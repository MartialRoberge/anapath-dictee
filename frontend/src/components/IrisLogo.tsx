/**
 * Iris logo — stylized iris diaphragm / flower
 * Three overlapping petals that form the microscope iris aperture.
 */

interface IrisLogoProps {
  size?: number;
  className?: string;
}

export function IrisLogo({ size = 28, className = "" }: IrisLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
    >
      {/* Three petals — iris diaphragm blades */}
      <path
        d="M16 3C17.5 8.5 22 12 16 16C10 12 14.5 8.5 16 3Z"
        fill="#0d9488"
        opacity="0.95"
      />
      <path
        d="M16 3C17.5 8.5 22 12 16 16C10 12 14.5 8.5 16 3Z"
        fill="#0d9488"
        opacity="0.7"
        transform="rotate(120 16 16)"
      />
      <path
        d="M16 3C17.5 8.5 22 12 16 16C10 12 14.5 8.5 16 3Z"
        fill="#0d9488"
        opacity="0.5"
        transform="rotate(240 16 16)"
      />
      {/* Center aperture */}
      <circle cx="16" cy="16" r="2.5" fill="#0d9488" />
    </svg>
  );
}

export function IrisWordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`font-sans font-bold tracking-tight ${className}`}>
      <span className="text-iris-600 dark:text-iris-400">Iris</span>
    </span>
  );
}
