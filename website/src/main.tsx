import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { ThemeProvider } from "./theme/ThemeProvider";
import { I18nProvider } from "./i18n/I18nProvider";
import { router } from "./router.tsx";
import "./styles/index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <I18nProvider>
        <RouterProvider router={router} />
      </I18nProvider>
    </ThemeProvider>
  </StrictMode>,
);
