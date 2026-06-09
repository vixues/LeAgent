# FastAPI scaffold

A minimal FastAPI service ready for the LeAgent coding agent.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the
interactive Swagger UI.

## Test

```bash
pytest tests/
```

When booted by the LeAgent supervisor the dev server binds to
`127.0.0.1` on a port allocated by the platform; the browser reaches
it through the signed reverse proxy at
`/api/v1/coding-projects/{id}/preview/...`.
