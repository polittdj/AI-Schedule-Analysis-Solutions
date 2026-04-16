# Runtime Broken By This Archive

This archive moved five items out of the active working tree on 2026-04-16 as
part of the rebuild housekeeping. The following runtime paths are BROKEN as a
result and will remain broken until the corresponding phases of the rebuild
complete and restore equivalent functionality.

## Launcher references into archived directories
run.bat:14:python -m app.main
run.sh:26:exec python3 -m app.main

## CI references into archived directories
.github/workflows/ci.yml:46:        run: python -m pytest tests/ -v --tb=short

## Expected restoration
- app/                  restored by rebuild Phases 2-11
- tests/                restored incrementally alongside each phase
- ollama/               restored by rebuild Phase 10
- scripts/start.ps1     superseded by rebuild Phase 12 (run.ps1 at repo root)
- PHASE-COMPLETE-HARDENING.md    preserved here for reference; not restored

Do not attempt to run run.bat or run.sh against this repo state expecting the
old behavior. The launcher will fail. This is expected. The rebuild will
produce a new launcher in Phase 12 that points at the rebuilt app/ tree.
