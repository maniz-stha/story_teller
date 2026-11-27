# Story approval before media production

## Intent

Let the owner read and accept each evaluated story before spending time on narration and rendering. Keep the existing final preview approval before download.

## Workflow

`queued → writing → evaluating → awaiting_story_approval → narrating → timing → rendering → copy → awaiting_review → approved`.

- The story review shows the script, title, summary, and evaluation. The owner may approve the current story revision or request story changes. An approval of an older revision returns a conflict and never queues media production.
- Story feedback creates a new revision and repeats writing, evaluation, and story approval. Feedback after a finished video follows the same path. Subtitle position feedback reuses the accepted story and audio, rerenders, then returns to final video review.
- A failed evaluation remains failed and retryable; it cannot be approved as a story. Failed media stages retry from the incomplete stage without requiring a second story approval.
- Final preview approval remains the only way to mark a video approved. Download remains limited to an approved revision. Earlier approved output remains available while a newer revision is pending, as it is today.

## Approaches

1. **Targeted pause and endpoint (chosen):** Add one run status and a revision checked story approval API action. Split the existing worker pass at evaluation, then resume the same revision after approval. Reuse story revision and final approval rules. This changes the fewest moving parts.
2. **Generic approval engine:** Persist arbitrary approval records and transition rules. It could support more checkpoints later, but adds a new framework for two fixed decisions.

## Scope and checks

Update worker and service state transitions, API, local review UI, tests, and current workflow documentation. Preserve existing run data and the `/approve` final approval contract; add a separate story approval action. Check stale approvals, no media before story approval, restart persistence, revision behavior, and download gating with mocked models and local test media. No new dependency or automatic publishing.
