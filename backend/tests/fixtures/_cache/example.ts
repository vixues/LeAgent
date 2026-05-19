interface Result { id: string; status: string; }

async function fetch_result(id: string): Promise<Result> {
  const r = await fetch(`/api/v1/tasks/${id}`);
  return r.json();
}
