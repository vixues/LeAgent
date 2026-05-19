# Python Project

A general-purpose Python project scaffolded by LeAgent.

## Project layout

```
main.py          # Entry point / dev server
src/
  __init__.py    # Package root
  utils.py       # Shared utilities
tests/
  test_utils.py  # Pytest suite
requirements.txt
```

## Run locally

```bash
pip install -r requirements.txt
python main.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) to see the project
status page.

## Test

```bash
pytest tests/
```

When managed by the LeAgent supervisor the dev server binds to
`127.0.0.1` on an allocated port; the browser reaches it through the
signed reverse proxy at `/api/v1/coding-projects/{id}/preview/...`.
