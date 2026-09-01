---
name: Python runtime setup
description: Replit environment guidance for imported Python projects whose package installation is blocked by the minimal runtime.
---

When an imported Python project has a minimal Python base but pip installation fails with an externally-managed-environment error or pip is missing, install a full `python-3.x` Replit tools module before installing project dependencies.

**Why:** The minimal base runtime may not include pip and cannot modify the immutable Nix store; the full tools module provides the supported package-install path.

**How to apply:** Check available Python modules first, choose a compatible full Python tools module, then install the project’s declared dependencies through the package-management tooling.