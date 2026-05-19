export function AmbientBackdrop() {
  return (
    <div
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      aria-hidden="true"
    >
      {/* Base wash — soft conic gradient suggesting depth */}
      <div
        className="absolute inset-0 opacity-[0.55]"
        style={{
          background:
            "radial-gradient(120% 80% at 50% 0%, var(--t-bg-wash-top) 0%, transparent 60%), radial-gradient(100% 60% at 50% 100%, var(--t-bg-wash-bottom) 0%, transparent 60%)",
        }}
      />

      {/* Aurora orb 1 — top right, cool */}
      <div
        className="aurora-orb absolute -top-[20%] -right-[10%] h-[90vh] w-[90vh] rounded-full mix-blend-screen dark:mix-blend-screen"
        style={{
          background:
            "radial-gradient(circle, var(--t-aurora-cool) 0%, transparent 60%)",
          filter: "blur(60px)",
          animation: "aurora-drift-1 38s ease-in-out infinite",
        }}
      />

      {/* Aurora orb 2 — bottom left, warm */}
      <div
        className="aurora-orb absolute -bottom-[25%] -left-[15%] h-[100vh] w-[100vh] rounded-full mix-blend-screen"
        style={{
          background:
            "radial-gradient(circle, var(--t-aurora-warm) 0%, transparent 60%)",
          filter: "blur(70px)",
          animation: "aurora-drift-2 52s ease-in-out infinite",
        }}
      />

      {/* Aurora orb 3 — center, brand */}
      <div
        className="aurora-orb absolute top-[20%] left-[15%] h-[70vh] w-[70vh] rounded-full mix-blend-screen"
        style={{
          background:
            "radial-gradient(circle, var(--t-aurora-brand) 0%, transparent 65%)",
          filter: "blur(80px)",
          animation: "aurora-drift-3 46s ease-in-out infinite",
        }}
      />

      {/* Aurora orb 4 — small accent, far right mid */}
      <div
        className="aurora-orb absolute top-[45%] -right-[5%] h-[50vh] w-[50vh] rounded-full mix-blend-screen"
        style={{
          background:
            "radial-gradient(circle, var(--t-aurora-violet) 0%, transparent 60%)",
          filter: "blur(90px)",
          animation: "aurora-drift-4 64s ease-in-out infinite",
        }}
      />

      {/* Volumetric beam — tilted soft band sweeping slowly */}
      <div
        className="aurora-beam absolute -inset-x-[20%] top-[20%] h-[80%] origin-center"
        style={{
          background:
            "linear-gradient(115deg, transparent 0%, transparent 35%, var(--t-aurora-beam) 50%, transparent 65%, transparent 100%)",
          filter: "blur(40px)",
          opacity: 0.7,
          animation: "beam-sweep 22s ease-in-out infinite alternate",
        }}
      />

      {/* Edge vignette for depth */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 90% at 50% 50%, transparent 50%, var(--t-vignette) 100%)",
        }}
      />

      {/* Film grain */}
      <svg
        className="absolute inset-0 h-full w-full opacity-[0.08] mix-blend-overlay"
        preserveAspectRatio="none"
      >
        <filter id="grain">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.9"
            numOctaves="2"
            stitchTiles="stitch"
          />
          <feColorMatrix
            type="matrix"
            values="0 0 0 0 0
                    0 0 0 0 0
                    0 0 0 0 0
                    0 0 0 0.6 0"
          />
        </filter>
        <rect width="100%" height="100%" filter="url(#grain)" />
      </svg>
    </div>
  );
}
