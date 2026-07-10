import { createHashRouter } from "react-router-dom";
import App from "./App";
import Home from "./pages/Home";
import About from "./pages/About";
import Workflows from "./pages/Workflows";
import Business from "./pages/Business";
import Download from "./pages/Download";
import Pets from "./pages/Pets";
import Company from "./pages/Company";

export const router = createHashRouter([
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
    ],
  },
]);
