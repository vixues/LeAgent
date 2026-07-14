import { createBrowserRouter } from "react-router-dom";
import App from "./App";
import Home from "./pages/Home";
import About from "./pages/About";
import Workflows from "./pages/Workflows";
import Business from "./pages/Business";
import Download from "./pages/Download";
import Pets from "./pages/Pets";
import Company from "./pages/Company";
import TutorialsLayout from "./pages/tutorials/TutorialsLayout";
import TutorialsIndex from "./pages/tutorials/TutorialsIndex";
import TutorialArticle from "./pages/tutorials/TutorialArticle";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Home /> },
      { path: "about", element: <About /> },
      { path: "workflows", element: <Workflows /> },
      { path: "business", element: <Business /> },
      { path: "download", element: <Download /> },
      { path: "pets", element: <Pets /> },
      { path: "company", element: <Company /> },
      {
        path: "tutorials",
        element: <TutorialsLayout />,
        children: [
          { index: true, element: <TutorialsIndex /> },
          {
            path: "intro",
            element: (
              <TutorialArticle fixedSection="intro" defaultSlug="overview" />
            ),
          },
          {
            path: ":section",
            element: <TutorialArticle defaultSlug="index" />,
          },
          {
            path: ":section/:slug",
            element: <TutorialArticle />,
          },
        ],
      },
    ],
  },
]);
