import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Full-viewport tech-style blurred gradient backdrop for splash-equivalent loading states.
 */
export function TechLoadingBackdrop({
  children,
  className,
}: {
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'relative min-h-screen w-full overflow-hidden bg-[#020617]',
        className,
      )}
    >
      {/* Base mesh */}
      <div
        className="pointer-events-none absolute inset-0 opacity-90"
        style={{
          backgroundImage: `
            radial-gradient(ellipse 80% 50% at 50% -20%, rgba(56, 189, 248, 0.35), transparent),
            radial-gradient(ellipse 60% 40% at 100% 50%, rgba(139, 92, 246, 0.2), transparent),
            radial-gradient(ellipse 50% 35% at 0% 80%, rgba(14, 165, 233, 0.25), transparent)
          `,
        }}
      />
      {/* Animated orbs (blur + drift) */}
      <div
        className="tech-orb-a pointer-events-none absolute -left-[20%] top-[15%] h-[55vmin] w-[55vmin] rounded-full bg-cyan-500/25 blur-[100px]"
        aria-hidden
      />
      <div
        className="tech-orb-b pointer-events-none absolute -right-[15%] bottom-[10%] h-[50vmin] w-[50vmin] rounded-full bg-violet-600/20 blur-[90px]"
        aria-hidden
      />
      <div
        className="tech-orb-c pointer-events-none absolute left-[35%] top-[45%] h-[35vmin] w-[35vmin] rounded-full bg-sky-400/15 blur-[80px]"
        aria-hidden
      />
      {/* Frosted veil */}
      <div className="pointer-events-none absolute inset-0 backdrop-blur-[2px] backdrop-saturate-150" aria-hidden />
      {/* Fine grid */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(148, 163, 184, 0.5) 1px, transparent 1px),
            linear-gradient(90deg, rgba(148, 163, 184, 0.5) 1px, transparent 1px)
          `,
          backgroundSize: '48px 48px',
          maskImage: 'radial-gradient(ellipse 70% 70% at 50% 50%, black 20%, transparent 75%)',
        }}
        aria-hidden
      />
      {/* Scan shimmer */}
      <div
        className="tech-scan pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          background:
            'linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.9) 50%, transparent 60%)',
          backgroundSize: '200% 100%',
        }}
        aria-hidden
      />
      <div className="relative z-10 flex min-h-screen w-full flex-col items-center justify-center px-4">
        {children}
      </div>
      <style>{`
        @keyframes techOrbA {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(12%, 8%) scale(1.08); }
          66% { transform: translate(-6%, 14%) scale(0.95); }
        }
        @keyframes techOrbB {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(-18%, -12%) scale(1.12); }
        }
        @keyframes techOrbC {
          0%, 100% { transform: translate(0, 0); opacity: 0.9; }
          40% { transform: translate(10%, -15%); opacity: 1; }
          70% { transform: translate(-12%, 10%); opacity: 0.85; }
        }
        @keyframes techScan {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        .tech-orb-a { animation: techOrbA 18s ease-in-out infinite; }
        .tech-orb-b { animation: techOrbB 22s ease-in-out infinite; }
        .tech-orb-c { animation: techOrbC 14s ease-in-out infinite; }
        .tech-scan { animation: techScan 12s linear infinite; }
        @media (prefers-reduced-motion: reduce) {
          .tech-orb-a, .tech-orb-b, .tech-orb-c, .tech-scan { animation: none; }
        }
      `}</style>
    </div>
  );
}
