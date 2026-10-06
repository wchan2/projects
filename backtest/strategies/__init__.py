"""Every module in this package that defines a `STRATEGY` is a strategy; main.py runs them all.

To add one: drop a new module here that exposes `STRATEGY = Strategy(...)`.
"""

import importlib
import pkgutil

from strategy import Strategy


def discover() -> dict[str, Strategy]:
    """module name -> Strategy, for every strategy module in this package."""
    found = {}
    for module in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f"{__name__}.{module.name}")
        if hasattr(mod, "STRATEGY"):
            found[module.name] = mod.STRATEGY
    return dict(sorted(found.items()))
