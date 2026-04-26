"""Windows-specific OS automation primitives.

Modules in this package may import Windows-only libraries (pywinauto,
uiautomation, winsdk). To keep the package importable in WSL for editing/testing,
those imports happen lazily inside functions, not at module top-level.
"""
