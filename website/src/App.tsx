import { Outlet } from "react-router-dom";
import { Layout } from "./components/Layout";

export default function App() {
  return (
    <Layout>
      <Outlet />
    </Layout>
  );
}
