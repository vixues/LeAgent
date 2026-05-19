import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs';
import { cn } from '@/lib/utils';

interface ApiModalProps {
  isOpen: boolean;
  onClose: () => void;
  flowId: string;
  flowName: string;
  endpoint: string;
}

type TabType = 'python' | 'javascript' | 'curl' | 'widget';

const generatePythonCode = (endpoint: string, flowId: string) => `import requests

url = "${endpoint}/api/v1/workflow/flows/${flowId}/run"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

payload = {
    "inputs": {
        "message": "Hello, this is a test message"
    }
}

response = requests.post(url, json=payload, headers=headers)
print(response.json())`;

const generateJavaScriptCode = (endpoint: string, flowId: string) => `const response = await fetch("${endpoint}/api/v1/workflow/flows/${flowId}/run", {
  method: "POST",
  headers: {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    inputs: {
      message: "Hello, this is a test message"
    }
  })
});

const data = await response.json();
console.log(data);`;

const generateCurlCode = (endpoint: string, flowId: string) => `curl -X POST "${endpoint}/api/v1/workflow/flows/${flowId}/run" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "inputs": {
      "message": "Hello, this is a test message"
    }
  }'`;

const generateWidgetCode = (endpoint: string, flowId: string) => `<!-- Add this snippet to your page -->
<script src="${endpoint}/widget.js"></script>
<div id="leagent-widget"></div>
<script>
  LeAgent.init({
    flowId: "${flowId}",
    container: "#leagent-widget",
    theme: "auto",
    locale: "en-US"
  });
</script>`;

export const ApiModal = ({
  isOpen,
  onClose,
  flowId,
  flowName,
  endpoint,
}: ApiModalProps) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<TabType>('python');
  const [copied, setCopied] = useState(false);

  const codeSnippets: Record<TabType, string> = {
    python: generatePythonCode(endpoint, flowId),
    javascript: generateJavaScriptCode(endpoint, flowId),
    curl: generateCurlCode(endpoint, flowId),
    widget: generateWidgetCode(endpoint, flowId),
  };

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(codeSnippets[activeTab]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  }, [activeTab, codeSnippets]);

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={t('modals.api.title')}
      size="lg"
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {t('modals.api.description', { name: flowName })}
          </p>
        </div>

        <Tabs
          defaultValue="python"
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as TabType)}
        >
          <div className="flex items-center justify-between mb-4">
            <TabsList>
              <TabsTrigger value="python">Python</TabsTrigger>
              <TabsTrigger value="javascript">JavaScript</TabsTrigger>
              <TabsTrigger value="curl">cURL</TabsTrigger>
              <TabsTrigger value="widget">{t('modals.api.widget')}</TabsTrigger>
            </TabsList>

            <Button
              variant="outline"
              size="sm"
              onClick={handleCopy}
              leftIcon={
                copied ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                )
              }
            >
              {copied ? t('common.copied') : t('common.copy')}
            </Button>
          </div>

          {(['python', 'javascript', 'curl', 'widget'] as const).map((tab) => (
            <TabsContent key={tab} value={tab}>
              <div className="relative">
                <pre
                  className={cn(
                    'p-4 rounded-lg bg-gray-900 text-gray-100 text-sm overflow-auto',
                    'max-h-80 font-mono'
                  )}
                >
                  <code>{codeSnippets[tab]}</code>
                </pre>
              </div>
            </TabsContent>
          ))}
        </Tabs>

        <div className="p-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
          <div className="flex gap-3">
            <svg
              className="w-5 h-5 text-amber-600 dark:text-amber-500 shrink-0 mt-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div className="text-sm text-amber-800 dark:text-amber-200">
              <p className="font-medium mb-1">{t('modals.api.apiKeyWarning')}</p>
              <p className="text-amber-700 dark:text-amber-300">
                {t('modals.api.apiKeyWarningDetail')}
              </p>
            </div>
          </div>
        </div>
      </div>
    </BaseModal>
  );
};

export default ApiModal;
