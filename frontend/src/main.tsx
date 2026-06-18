import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import { initI18n } from './i18n';
/** Global Tailwind layers first so route-level CSS (e.g. React Flow, code highlight) can override when needed. */
import './styles/globals.css';
import './styles/chat.css';
import 'katex/dist/katex.min.css';
import { queryClient } from '@/lib/queryClient';
import { ProductMetaProvider } from '@/hooks/useProductMeta';

const container = document.getElementById('root');
if (!container) throw new Error('Root element not found');

const routerBasename = import.meta.env.BASE_URL.startsWith('/')
  ? import.meta.env.BASE_URL
  : '/';

void initI18n().then(() => {
  createRoot(container).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ProductMetaProvider>
          <BrowserRouter basename={routerBasename}>
            <App />
          </BrowserRouter>
        </ProductMetaProvider>
      </QueryClientProvider>
    </StrictMode>
  );
});
