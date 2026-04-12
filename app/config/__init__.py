"""
Config package - re-export from config_loader to provide 'from app.config import config'.

The 'app.config' package was previously broken because it had:
  - No __init__.py (causing Python to not recognize it as a package)
  - A nested 'config/' subdirectory with a broken/missing __init__.py
  - Sibling modules that imported from 'app.config.defaults' (wrong path)

We fix it by re-exporting the working config from app.config_loader.
This makes 'from app.config import config' work for any module that
currently imports from the broken nested package.
"""
from app.config_loader import config  # noqa: E402
