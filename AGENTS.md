# Project Agent Instructions

## Project context
- Read docs/product-requirements.md for product behavior.
- Read docs/architecture-proposal.md for proposed implementation.
- Read plans/current.md for the active task.

## Engineering principles
- Follow the existing architecture and conventions.
- Prefer simple, maintainable solutions.
- Do not introduce new dependencies without justification.
- Avoid unrelated refactoring.
- Do not duplicate existing functionality.
- Do not silently change public API contracts.

## Workflow
1. Inspect relevant code and documentation.
2. Clarify ambiguous requirements.
3. Plan complex changes before implementation.
4. Implement only the approved task.
5. Add or update relevant tests.
6. Run lint, type checks, and tests.
7. Review the diff for unintended changes.
8. Summarize changes and verification results.

## Safety
- Never commit credentials or secrets.
- Do not run destructive database commands without approval.
- Do not modify production infrastructure without approval.
- Do not claim tests passed unless they were executed.

## Completion
Report:
- Files changed
- Key decisions
- Tests executed and results
- Remaining issues or risks
- Documentation requiring updates
