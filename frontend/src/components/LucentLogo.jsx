export function LucentGlyph({ className = '', size = 36 }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 80 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <polygon
        points="40,10 70,40 40,70 10,40"
        fill="none"
        stroke="currentColor"
        strokeWidth="4.5"
        strokeLinejoin="round"
      />
      <polygon points="40,22 58,40 40,58 22,40" fill="currentColor" />
      <line
        x1="40"
        y1="12"
        x2="40"
        y2="22"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <line
        x1="40"
        y1="58"
        x2="40"
        y2="68"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  )
}

export default function LucentLogo({ compact = false }) {
  return (
    <span className="lucent-lockup">
      <span className="lucent-glyph-wrap" aria-hidden="true">
        <LucentGlyph size={compact ? 26 : 32} />
      </span>
      <span className="lucent-wordmark">LUCENT</span>
    </span>
  )
}
