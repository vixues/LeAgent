"""Self-hosted diffusion models (Stable Diffusion / SDXL + LoRA).

Requires the optional ``diffusion`` dependency group::

    cd backend && uv sync --extra diffusion

The adapter is import-gated: when ``torch``/``diffusers`` are missing the
package imports fine but :func:`diffusers_available` returns ``False`` and no
``Model.image_gen.local`` node is registered.
"""

from __future__ import annotations


def diffusers_available() -> bool:
    """Return True when the optional diffusion stack is importable."""
    try:
        import diffusers  # noqa: F401
        import torch  # noqa: F401
    except Exception:  # noqa: BLE001 - any import error means unavailable
        return False
    return True


__all__ = ["diffusers_available"]
