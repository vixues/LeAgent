import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  GitBranch, 
  Clock, 
  TrendingUp, 
  ArrowRight,
  LayoutGrid,
  List,
  Play,
  Edit3,
  Trash2,
  MoreVertical,
  Calendar,
  CheckCircle2,
} from 'lucide-react';
import { Button, Card, CardContent } from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import { PageLoader } from '@/components/common/PageLoader';
import { EmptyState } from '@/components/common/EmptyState';
import { useRecentFlows, useHomeStats } from '@/hooks/useHome';
import { formatRelativeTime, cn } from '@/lib/utils';

type ViewMode = 'grid' | 'list';

export default function HomePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: recentFlows, isLoading: flowsLoading } = useRecentFlows();
  const { data: stats, isLoading: statsLoading } = useHomeStats();
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  const quickActions = [
    {
      id: 'new-flow',
      icon: GitBranch,
      title: t('home.quickActions.newFlow'),
      description: t('home.quickActions.newFlowDesc'),
      color:
        'bg-primary-100 text-primary-800 dark:bg-primary-900/30 dark:text-primary-300',
      onClick: () => navigate('/workflows/new'),
    },
  ];

  const statCards = [
    {
      id: 'total-flows',
      label: t('home.stats.totalFlows'),
      value: stats?.totalFlows || 0,
      icon: GitBranch,
      color: 'text-sky-600 dark:text-sky-400',
      bgColor: 'bg-sky-100 dark:bg-sky-900/30',
    },
    {
      id: 'running-tasks',
      label: t('home.stats.runningTasks'),
      value: stats?.runningTasks || 0,
      icon: Clock,
      color: 'text-peach-600 dark:text-peach-400',
      bgColor: 'bg-peach-100 dark:bg-peach-900/30',
    },
    {
      id: 'completed-today',
      label: t('home.stats.completedToday'),
      value: stats?.completedToday || 0,
      icon: TrendingUp,
      color: 'text-mint-600 dark:text-mint-400',
      bgColor: 'bg-mint-100 dark:bg-mint-900/30',
    },
  ];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
      case 'draft':
        return 'bg-surface-sunken text-muted-foreground';
      case 'paused':
        return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
      case 'error':
        return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';
      default:
        return 'bg-surface-sunken text-muted-foreground';
    }
  };

  const handleRunFlow = (e: React.MouseEvent, flowId: string) => {
    e.stopPropagation();
    navigate(`/workflows/${flowId}?action=run`);
  };

  const handleEditFlow = (e: React.MouseEvent, flowId: string) => {
    e.stopPropagation();
    navigate(`/workflows/${flowId}`);
  };

  const handleDeleteFlow = (e: React.MouseEvent, flowId: string) => {
    e.stopPropagation();
    if (window.confirm(t('workflow.confirmDelete'))) {
      console.log('Delete flow:', flowId);
    }
    setMenuOpenId(null);
  };

  return (
    <PageShell
      title={`${t('home.welcome')} 👋`}
      description={t('home.subtitle')}
    >
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {statCards.map((stat) => (
            <Card key={stat.id} className="hover:shadow-md transition-shadow">
              <CardContent className="flex items-center gap-4">
                <div className={`p-3 rounded-xl ${stat.bgColor}`}>
                  <stat.icon className={`w-6 h-6 ${stat.color}`} />
                </div>
                <div className="flex-1 text-center sm:text-left">
                  <p className="text-sm text-muted-foreground">{stat.label}</p>
                  <p className="text-2xl font-bold text-foreground">
                    {statsLoading ? '-' : stat.value}
                  </p>
                </div>
              </CardContent>
            </Card>
          ))}
      </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <div className="flex items-center justify-between p-4 border-b border-border">
                <h2 className="text-2xl font-semibold text-foreground">
                  {t('home.recentFlows')}
                </h2>
                <div className="flex items-center gap-2">
                  <div className="flex items-center bg-surface-sunken rounded-lg p-1">
                    <button
                      onClick={() => setViewMode('grid')}
                      className={cn(
                        'p-1.5 rounded-md transition-colors',
                        viewMode === 'grid'
                          ? 'bg-surface-elevated shadow-sm text-primary-600 dark:text-primary-400'
                          : 'text-muted-foreground hover:text-foreground'
                      )}
                      title={t('home.viewGrid')}
                    >
                      <LayoutGrid className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => setViewMode('list')}
                      className={cn(
                        'p-1.5 rounded-md transition-colors',
                        viewMode === 'list'
                          ? 'bg-surface-elevated shadow-sm text-primary-600 dark:text-primary-400'
                          : 'text-muted-foreground hover:text-foreground'
                      )}
                      title={t('home.viewList')}
                    >
                      <List className="w-4 h-4" />
                    </button>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigate('/workflows')}
                    rightIcon={<ArrowRight className="w-4 h-4" />}
                  >
                    {t('common.more')}
                  </Button>
                </div>
              </div>
              <CardContent padding="none">
                {flowsLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <PageLoader size="md" message={t('common.loading')} />
                  </div>
                ) : recentFlows && recentFlows.length > 0 ? (
                  viewMode === 'grid' ? (
                    <div className="p-4 grid gap-4 sm:grid-cols-2">
                      {recentFlows.slice(0, 6).map((flow) => (
                        <div
                          key={flow.id}
                          className="group relative p-4 rounded-xl border border-border hover:border-primary-300 dark:hover:border-primary-700 hover:shadow-sm cursor-pointer transition-[color,background-color,border-color,box-shadow,opacity,transform] bg-surface"
                          onClick={() => navigate(`/workflows/${flow.id}`)}
                        >
                          <div className="flex flex-col items-center text-center mb-3">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary-100 to-primary-200 dark:from-primary-900/30 dark:to-primary-800/30 flex items-center justify-center mb-3">
                              <GitBranch className="w-6 h-6 text-primary-600 dark:text-primary-400" />
                            </div>
                            <h3 className="font-semibold text-foreground truncate w-full">
                              {flow.name}
                            </h3>
                            <span className={cn(
                              'mt-2 px-2.5 py-0.5 rounded-full text-xs font-medium',
                              getStatusColor(flow.status)
                            )}>
                              {t(`workflow.status.${flow.status}`)}
                            </span>
                          </div>
                          
                          <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground mb-3">
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3.5 h-3.5" />
                              {formatRelativeTime(flow.updatedAt)}
                            </span>
                            {flow.nodeCount && (
                              <span className="flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                {t('workflow.nodeCountLabel', { count: flow.nodeCount })}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={(e) => handleRunFlow(e, flow.id)}
                              className="flex-1"
                              leftIcon={<Play className="w-3.5 h-3.5" />}
                            >
                              {t('workflow.run')}
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={(e) => handleEditFlow(e, flow.id)}
                            >
                              <Edit3 className="w-3.5 h-3.5" />
                            </Button>
                            <div className="relative">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setMenuOpenId(menuOpenId === flow.id ? null : flow.id);
                                }}
                              >
                                <MoreVertical className="w-3.5 h-3.5" />
                              </Button>
                              {menuOpenId === flow.id && (
                                <>
                                  <div
                                    className="fixed inset-0 z-10"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setMenuOpenId(null);
                                    }}
                                  />
                                  <div className="absolute right-0 top-full mt-1 z-20 bg-surface border border-border rounded-lg shadow-lg py-1 min-w-[100px]">
                                    <button
                                      className="w-full px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 flex items-center gap-2"
                                      onClick={(e) => handleDeleteFlow(e, flow.id)}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                      {t('common.delete')}
                                    </button>
                                  </div>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="divide-y divide-border">
                      {recentFlows.slice(0, 5).map((flow) => (
                        <div
                          key={flow.id}
                          className="group flex items-center justify-between p-4 hover:bg-surface-sunken/80 cursor-pointer transition-colors"
                          onClick={() => navigate(`/workflows/${flow.id}`)}
                        >
                          <div className="flex items-center gap-3 min-w-0 flex-1">
                            <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                              <GitBranch className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="font-medium text-foreground truncate">
                                {flow.name}
                              </p>
                              <p className="text-sm text-muted-foreground">
                                {formatRelativeTime(flow.updatedAt)}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className={cn(
                              'px-2.5 py-0.5 rounded-full text-xs font-medium',
                              getStatusColor(flow.status)
                            )}>
                              {t(`workflow.status.${flow.status}`)}
                            </span>
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              <Button
                                variant="primary"
                                size="sm"
                                onClick={(e) => handleRunFlow(e, flow.id)}
                                leftIcon={<Play className="w-3.5 h-3.5" />}
                              >
                                {t('workflow.run')}
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={(e) => handleEditFlow(e, flow.id)}
                              >
                                <Edit3 className="w-3.5 h-3.5" />
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                ) : (
                  <EmptyState
                    icon={<GitBranch className="w-12 h-12" />}
                    title={t('home.noFlows')}
                    action={{
                      label: t('home.createFirstFlow'),
                      onClick: () => navigate('/workflows/new'),
                    }}
                  />
                )}
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <div className="p-4 border-b border-border">
                <h2 className="text-2xl font-semibold text-foreground text-center">
                  {t('home.quickActions.title')}
                </h2>
              </div>
              <CardContent className="space-y-3" padding="sm">
                {quickActions.map((action) => (
                  <button
                    key={action.id}
                    onClick={action.onClick}
                    className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-surface-sunken/80 transition-colors text-left"
                  >
                    <div className={`p-2.5 rounded-lg ${action.color}`}>
                      <action.icon className="w-5 h-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-foreground">
                        {action.title}
                      </p>
                      <p className="text-sm text-muted-foreground truncate">
                        {action.description}
                      </p>
                    </div>
                  </button>
                ))}
              </CardContent>
            </Card>

            <Card className="bg-gradient-to-br from-primary-500 to-primary-700 border-0">
              <CardContent>
                <div className="text-white text-center">
                  <h3 className="font-semibold text-lg mb-2">{t('home.tips.title')}</h3>
                  <p className="text-primary-100 text-sm mb-4">
                    {t('home.tips.description')}
                  </p>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="bg-white/20 hover:bg-white/30 text-white border-0"
                    onClick={() => navigate('/docs')}
                  >
                    {t('home.tips.learnMore')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
    </PageShell>
  );
}
