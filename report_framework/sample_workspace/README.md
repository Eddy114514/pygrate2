This directory is a manual sample workspace for `report_framework`.

- `tests/` contains automated `unittest` suites and does not require the UI.
- `sample_workspace/` contains runnable sample files for warning analysis, preview apply, and UI demos.

Files:
- `basic_warnings.py`: syntax and builtin-style warnings plus simple auto-fixes.
- `semantic_warnings.py`: metadata-driven semantic warnings and auto-fixes.
- `folderA/runtime_only_warnings.py`: warnings that are mainly useful for runtime inspection or manual UI review.
