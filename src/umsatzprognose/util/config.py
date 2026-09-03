from __future__ import annotations

import importlib.util


def in_colab() -> bool:
    """Ob der Code in Google Colab laeuft."""
    return (
        importlib.util.find_spec("google") is not None
        and importlib.util.find_spec("google.colab") is not None
    )
