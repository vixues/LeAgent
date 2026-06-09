import { useState } from 'react';

export default function App() {
  const [count, setCount] = useState(0);

  return (
    <main className="container">
      <header>
        <h1>Vite + React</h1>
        <p className="subtitle">A LeAgent scaffold ready for the coding agent.</p>
      </header>
      <section className="card">
        <button type="button" onClick={() => setCount((c) => c + 1)}>
          Count is {count}
        </button>
        <p className="hint">
          Edit <code>src/App.tsx</code> and save to reload via HMR.
        </p>
      </section>
    </main>
  );
}
