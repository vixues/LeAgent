import { Routes, Route, Navigate, useParams } from 'react-router-dom';
import { useEffect, Suspense } from 'react';
import { useTranslation } from 'react-i18next';

import { useThemeStore } from './stores/theme';
import { useChatStore } from './stores/chat';
import { isUuid } from './lib/utils';
import { AppShell } from './components/layout/AppShell';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { PageLoader } from './components/common/PageLoader';
import { TechLoadingBackdrop } from './components/common/TechLoadingBackdrop';
import { ToastProvider, Toaster } from './components/ui/Toaster';
import {
  ChatView,
  HomePage,
  DashboardPage,
  WorkflowsPage,
  ExecutionPage,
  CronPage,
  TemplatesPage,
  PlaygroundPage,
  KnowledgePage,
  ToolsPage,
  MCPPage,
  SkillsPage,
  WebhooksPage,
  ChannelsPage,
  RulesPage,
  AdminPage,
  SettingsPage,
  DocsPage,
  FolderPage,
  TasksPage,
  PetSpacePage,
} from './routes/lazyPages';
import { AuthGatePage } from './pages/AuthGatePage';
import { ProtectedRoute } from './components/authorization/ProtectedRoute';

function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-gray-900 dark:text-white">404</h1>
        <p className="mt-4 text-gray-600 dark:text-gray-400">{t('errors.notFound')}</p>
      </div>
    </div>
  );
}

function AppSuspenseFallback() {
  const { t } = useTranslation();
  return (
    <TechLoadingBackdrop>
      <div className="rounded-2xl border border-white/10 bg-slate-900/40 px-10 py-8 shadow-2xl backdrop-blur-md">
        <PageLoader
          size="lg"
          message={t('common.meta.starting')}
          className="text-slate-100 [&_p]:text-slate-300"
        />
      </div>
    </TechLoadingBackdrop>
  );
}

function ChatSessionRoute() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const selectSession = useChatStore((state) => state.selectSession);

  useEffect(() => {
    if (sessionId && isUuid(sessionId)) selectSession(sessionId);
  }, [sessionId, selectSession]);

  return <Navigate to="/home" replace />;
}

export default function App() {
  const initializeTheme = useThemeStore((s) => s.initializeTheme);

  useEffect(() => {
    initializeTheme();
  }, [initializeTheme]);

  return (
    <ToastProvider>
      <Toaster position="top-right" />
      <ErrorBoundary showDetails>
        <Suspense fallback={<AppSuspenseFallback />}>
          <Routes>
            <Route path="/about" element={<Navigate to="/home" replace />} />
            <Route path="/login" element={<AuthGatePage />} />
            <Route path="/setup" element={<AuthGatePage />} />

            <Route path="/chat/:sessionId" element={<ChatSessionRoute />} />

            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <AppShell />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/home" replace />} />

              <Route path="home" element={<ChatView />} />
              <Route path="chat" element={<Navigate to="/home" replace />} />

              <Route path="overview" element={<HomePage />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="workflow" element={<Navigate to="/workflows" replace />} />
              <Route path="template" element={<Navigate to="/templates" replace />} />
              {/* Unified workflow page: hub (list + chat templates) and editor */}
              <Route path="workflows" element={<WorkflowsPage />} />
              <Route
                path="workflows/templates"
                element={<Navigate to="/workflows?tab=playbooks" replace />}
              />
              <Route path="workflows/new" element={<WorkflowsPage />} />
              <Route path="workflows/:id/executions" element={<WorkflowsPage />} />
              <Route path="workflows/:id" element={<WorkflowsPage />} />
              <Route path="executions/:executionId" element={<ExecutionPage />} />
              <Route path="templates" element={<TemplatesPage />} />
              <Route path="cron" element={<CronPage />} />
              <Route path="tasks" element={<TasksPage />} />
              <Route path="tasks/:taskId" element={<TasksPage />} />
              <Route path="playground" element={<PlaygroundPage />} />
              <Route
                path="chat-workflow-templates"
                element={<Navigate to="/workflows?tab=playbooks" replace />}
              />
              <Route path="pet-space" element={<PetSpacePage />} />
              <Route path="knowledge" element={<KnowledgePage />} />
              <Route path="tools" element={<ToolsPage />} />
              <Route path="mcp" element={<MCPPage />} />
              <Route path="skills" element={<SkillsPage />} />
              <Route path="settings/skills" element={<Navigate to="/skills" replace />} />
              <Route path="webhooks" element={<WebhooksPage />} />
              <Route path="channels" element={<ChannelsPage />} />
              <Route path="rules" element={<RulesPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="folders" element={<FolderPage />} />
              <Route path="coding-projects" element={<Navigate to="/folders" replace />} />
              <Route path="docs" element={<DocsPage />} />
              <Route path="admin" element={<AdminPage />} />

              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </ToastProvider>
  );
}
