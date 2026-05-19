import { memo, useMemo, useRef } from 'react';
import { usePetSceneController } from '@/hooks/usePetSceneController';
import { usePetAppearancePreview, type PetAppearanceProjectContext } from '@/hooks/usePetAppearancePreview';
import { usePetDockPreview } from '@/hooks/usePetDockPreview';
import { BrandMascot } from '@/components/brand/BrandMascot';
import { cn } from '@/lib/utils';
import {
  DEFAULT_DOCK_FLOOR_Y_PX,
  DEFAULT_DOCK_SHADOW_OFFSET_Y_PX,
  DOCK_FLOOR_Y_MAX,
  DOCK_FLOOR_Y_MIN,
  DOCK_SHADOW_OFFSET_Y_MAX,
  DOCK_SHADOW_OFFSET_Y_MIN,
  resolvedNest,
  type PetSettings,
} from '@/lib/petSettings';

export type PetSceneSurface = 'dock' | 'hero' | 'chatEmpty';

type PetSceneStageProps = {
  surface: PetSceneSurface;
  projectContext?: PetAppearanceProjectContext | null;
  settings?: PetSettings;
  collapsed?: boolean;
  className?: string;
  /** When set with `surface="dock"`, open Pet Space / pet reactions only register on the pet graphic (not the full yard). */
  onDockActivate?: () => void;
  dockAriaLabel?: string;
};

const floorVar: Record<PetSceneSurface, string> = {
  dock: '5px',
  hero: '12px',
  chatEmpty: '10px',
};

export const PetSceneStage = memo(function PetSceneStage({
  surface,
  projectContext,
  settings: settingsProp,
  collapsed,
  className,
  onDockActivate,
  dockAriaLabel,
}: PetSceneStageProps) {
  const { data: dock } = usePetDockPreview();
  const settings: PetSettings = projectContext?.settings ?? settingsProp ?? dock?.settings ?? {};
  const stageRef = useRef<HTMLDivElement | null>(null);
  const scene = usePetSceneController({ settings, stageRef, surface });
  const preview = usePetAppearancePreview({
    overrideVisual: scene.overrideVisual,
    projectContext: projectContext ?? undefined,
  });
  const {
    previewUrl,
    motionClass,
    motionStyle,
    reduceMotion: previewReduce,
    clipMirror,
    clipObjectFit,
    previewShellClass,
    appearanceLoading,
  } = preview;
  const objectFit = clipObjectFit === 'cover' ? 'object-cover' : 'object-contain';
  /** Facing (±1) × per-clip mirror, matching PetDockWidget. */
  const scaleX = scene.facing * (clipMirror ? -1 : 1);
  const shadowY = -scene.y;
  const shadowScaleX = 1 - Math.min(0.5, Math.max(0, shadowY / 40));
  const dockPetTargetOnly = surface === 'dock' && Boolean(onDockActivate);
  const floorYCss = useMemo(() => {
    if (surface === 'dock') {
      const n = resolvedNest(settings);
      const raw = Number(n.dockFloorYPx);
      const px = Math.round(
        Math.min(DOCK_FLOOR_Y_MAX, Math.max(DOCK_FLOOR_Y_MIN, Number.isFinite(raw) ? raw : DEFAULT_DOCK_FLOOR_Y_PX)),
      );
      return `${px}px`;
    }
    return floorVar[surface];
  }, [surface, settings]);

  const dockShadowOffsetPx = useMemo(() => {
    if (surface !== 'dock') return 0;
    const n = resolvedNest(settings);
    const raw = Number(n.dockShadowOffsetYPx);
    return Math.round(
      Math.min(
        DOCK_SHADOW_OFFSET_Y_MAX,
        Math.max(
          DOCK_SHADOW_OFFSET_Y_MIN,
          Number.isFinite(raw) ? raw : DEFAULT_DOCK_SHADOW_OFFSET_Y_PX,
        ),
      ),
    );
  }, [surface, settings]);

  const imgClass = cn(
    'select-none',
    objectFit,
    surface === 'dock' &&
      (collapsed ? 'h-10 w-10' : 'h-auto w-auto max-h-[4.5rem] max-w-[4.5rem] rounded-lg sm:max-h-[4.75rem] sm:max-w-[4.75rem]'),
    surface === 'hero' && 'h-full w-full',
    surface === 'chatEmpty' && 'h-full w-full rounded-lg',
  );
  const mascotWrapClass = cn(
    'inline-flex items-end justify-center',
    surface === 'dock' &&
      (collapsed ? 'h-10 w-10' : 'inline-flex max-h-[4.5rem] max-w-[4.5rem] sm:max-h-[4.75rem] sm:max-w-[4.75rem]'),
  );

  const petGraphic = previewUrl ? (
    <img src={previewUrl} alt="" draggable={false} className={imgClass} />
  ) : appearanceLoading ? (
    <span className={cn(mascotWrapClass, 'min-h-[2.5rem] min-w-[2.5rem]')} aria-hidden />
  ) : (
    <span className={mascotWrapClass}>
      <BrandMascot size={surface === 'hero' ? 'lg' : 'md'} staticFallback={previewReduce} aria-hidden />
    </span>
  );

  const petBody = dockPetTargetOnly ? (
    <button
      type="button"
      className={cn(
        'inline-flex max-w-full max-h-full items-end justify-center border-0 bg-transparent p-0',
        'cursor-pointer rounded-lg transition-colors',
        'hover:bg-black/[0.04] dark:hover:bg-white/[0.04]',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
      )}
      aria-label={dockAriaLabel}
      onClick={scene.onPetClick}
      onDoubleClick={scene.onPetDoubleClick}
    >
      {petGraphic}
    </button>
  ) : (
    petGraphic
  );

  return (
    <div
      ref={stageRef}
      className={cn(
        'pet-scene',
        `pet-scene--${surface}`,
        previewUrl && previewShellClass,
        !previewUrl &&
          !appearanceLoading &&
          surface === 'dock' &&
          !collapsed &&
          'border border-border-subtle bg-background/80',
        className,
      )}
      data-surface={surface}
      data-collapsed={collapsed ? '1' : '0'}
      style={{ '--pet-scene-floor-y': floorYCss } as React.CSSProperties}
      onClick={dockPetTargetOnly ? () => onDockActivate?.() : undefined}
    >
      <div className="pet-scene__floor" aria-hidden />
      <div
        className="pet-scene__shadow"
        aria-hidden
        style={{
          transform: `translate3d(${scene.x}px,${dockShadowOffsetPx}px,0) scaleX(${Math.max(0.35, shadowScaleX)})`,
          opacity: Math.max(0.2, 0.55 - shadowY * 0.012),
        }}
      />
      <div
        className={cn('pet-scene__translate', dockPetTargetOnly && 'pointer-events-none')}
        style={{ transform: `translate3d(${scene.x}px, ${scene.y}px, 0) scaleX(${scaleX})` }}
        onClick={dockPetTargetOnly ? undefined : scene.onPetClick}
        onDoubleClick={dockPetTargetOnly ? undefined : scene.onPetDoubleClick}
        onKeyDown={
          dockPetTargetOnly
            ? undefined
            : (e) => {
                if (e.key === 'Enter' || e.key === ' ') e.stopPropagation();
              }
        }
        role="presentation"
      >
        <div className={cn('pet-scene__body', dockPetTargetOnly && 'pointer-events-none', motionClass)} style={motionStyle}>
          {dockPetTargetOnly ? (
            <span className="pointer-events-auto inline-flex max-h-full max-w-full items-end justify-center">{petBody}</span>
          ) : (
            petBody
          )}
        </div>
      </div>
    </div>
  );
});
