// JS example
const API = 'http://localhost:7860/api/v1';

async function run(q) {
  const r = await fetch(`${API}/chat`);
  return r.json();
}
