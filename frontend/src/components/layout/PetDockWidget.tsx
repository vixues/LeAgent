import { memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { PetSceneStage } from '@/components/pet/PetSceneStage';

interface PetDockWidgetProps {
  collapsed: boolean;
  active: boolean;
}

export const PetDockWidget = memo(function PetDockWidget({ collapsed, active }: PetDockWidgetProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const go = () => {
    navigate('/pet-space');
  };

  const dockAria = t('petSpace.dockAria', { defaultValue: 'Pet Space' });

  if (collapsed) {
    return (
      <div
        className={cn(
          'flex w-full flex-col items-center justify-center rounded-lg p-0.5 min-h-0 transition-colors',
          'bg-transparent',
        )}
      >
        <div className="h-10 w-10 min-h-0 min-w-0 overflow-visible">
          <PetSceneStage
            surface="dock"
            collapsed
            className="h-full w-full"
            onDockActivate={go}
            dockAriaLabel={dockAria}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'relative flex w-full flex-col overflow-visible rounded-lg p-2 transition-colors',
        'min-h-[5.75rem] sm:min-h-[6.25rem]',
        active && 'bg-primary-50/25 dark:bg-primary-950/15',
      )}
    >
      <PetSceneStage
        surface="dock"
        className="pet-scene--dock-yard min-h-[5rem] w-full flex-1 sm:min-h-[5.5rem]"
        onDockActivate={go}
        dockAriaLabel={dockAria}
      />
    </div>
  );
});
