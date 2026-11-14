# Story video generator — product requirements

**Status:** Draft for owner review

**Date:** 2026-11-13

**Product owner and sole user:** Manish

## 1. Purpose

Generate short, first-person story videos from a small set of inputs, with narration, timed subtitles, and randomly selected user-supplied background footage. The local app should do the production work and present a finished draft for review. After approval, it should provide a video and posting copy for manual upload to YouTube Shorts, Instagram Reels, and TikTok.

## 2. Goals and boundaries

### Phase-one goals

- Start a generation on demand from either a command line or a local web interface.
- Generate original stories using a selected Ollama or OpenAI model, then evaluate and automatically revise weak drafts.
- Produce one portrait video with local narration, burned-in subtitles, and a randomly chosen uploaded background clip.
- Allow feedback on the story or subtitle position, rebuild the affected stages, and require approval of the latest preview.
- Save the approved video and generated, platform-specific titles, captions, and hashtags for manual posting.
- Use previous story summaries automatically to reduce repeated plots and twists.

### Out of scope for phase one

- Scheduled or unattended generation, hosted execution, and automatic publishing.
- Multiple character voices, languages other than English, or perspectives other than first person as validated production presets.
- Stock footage sourcing, generated background footage, and automatic performance-driven optimization.

**Success means** the owner can generate, review, revise, approve, and manually post a complete video without editing media files by hand. View counts are not a phase-one acceptance criterion: an AI story score cannot reliably predict audience engagement by itself.

## 3. User and operating context

- One user on their own computer. Runs begin only when that computer is on and the user initiates them.
- The same pipeline serves the command line and local web interface; drafts and settings are shared. The proposed web default is accessible only on the owner's computer, with no login for this single-user phase.
- Story writing and evaluation default to local Ollama models, with optional OpenAI models selected independently for writing, evaluation, and posting copy. Narration, subtitle timing, and rendering run locally. The code in `samples/` is experimental reference material, not a finished implementation.
- The app stores uploaded clips, run settings, story versions, previews, approvals, and final outputs locally.

## 4. Inputs and defaults

All listed fields can be edited in saved settings and overridden for a run. Saved defaults apply unless overridden. English and first person are the validated phase-one values for language and perspective; other values are experimental until voice and output quality are tested.

| Field | Phase-one behavior and default |
| --- | --- |
| Theme | Randomly pick from **workplace drama, family conflict, everyday mystery, betrayal, wholesome surprise**. The user can choose any of those or enter **other** with a custom theme. Never pick `other` randomly. |
| Target narration duration | 90 seconds. |
| Narration speed | Target 260 spoken words per minute by default. This informs the script word budget and final audio duration; measure the produced audio before rendering. |
| Tone | Determined by the chosen theme, aiming for suspenseful, believable, emotionally engaging writing where appropriate. User may override it. |
| Perspective | First person. |
| Audience and language | General adult audience; conversational English. |
| Optional premise | Blank by default; when supplied, it steers the plot. |
| Recent plots or twists to avoid | Automatically derived from short summaries of prior stories; user can add exclusions for a run. The proposed initial source is approved stories. |
| Narrator voice | Female by default. Use a male voice when the generated story explicitly has a male narrator. Store narrator identity with the story instead of guessing it later from the prose. Initial voice references are `samples/female_voice_reference.mp3` and `samples/male_voice_reference.mp3`; test their quality before production use. |
| Background clip | Random selection from the user's uploaded clip library. |
| Intended platforms | All three selected by default for posting copy; user can change selection before approval. Phase one does not publish. |

The earlier examples of moral dilemmas and short suspense are writing guidance, not additional theme values. At 90 seconds and 260 words per minute, the initial script target is approximately 390 spoken words; allow a 10% script-length tolerance. The final audio duration is authoritative.

The story follows a hook, setup with personal stakes, connected escalation, a costly choice, an earned payoff, and a closing line tied to an earlier detail. It should be complete, believable, and written for listening in short paragraphs. The writer returns a story title, narration, word count, estimated duration, and a continuity note; the app measures the count and duration from the final narration text. The full writing rubric is in [`story_prompt.txt`](../src/story_teller/story_prompt.txt).

## 5. End-to-end workflow

1. **Prepare:** The user uploads one or more background clips, sets defaults, and starts a run from the CLI or local web app. The app records the resolved input values and randomly selected theme for reproducibility.
2. **Plan and write:** A story-writing agent creates a brief plot plan and first-person script. It records the narrator's intended identity and a concise plot/twist summary. The prompt includes recent stories to avoid, the selected theme, optional premise, tone, and word budget.
3. **Evaluate and revise:** A separate story-evaluation step checks coherence, believable causality, opening hook, pacing, satisfying ending, adherence to inputs, and similarity to recent plots. Deterministic checks cover required fields and approximate length. On failure, revise automatically with evaluator feedback, with a finite retry limit. If no draft passes, save a flagged story draft and a reason; do not continue to audio or silently mark the run complete.
4. **Narrate:** Choose the female or male local narrator voice from story metadata. Generate audio, measure its duration, and correct material duration or speech-quality problems before proceeding. The stored script and audio must remain associated with the same story version.
5. **Time subtitles:** Derive word timing from the *final* narration audio, after any speed adjustment. Compare the recognized words with the script and flag material omissions or additions. Default to groups of five to seven words, allowing shorter groups at pauses, sentence endings, or line-length limits. Save the timed subtitle data separately from its visual position.
6. **Render:** Pick an uploaded clip randomly, mute its original audio, and fit it into a portrait frame. Use the final story-audio duration as the video duration: trim a longer background clip at that point; loop a shorter clip and trim the last repeat at that point. Mix the narration and burn in readable subtitles. Check the resulting video for valid audio, dimensions, subtitle presence, and an ending that matches the audio (allowing only frame/codec rounding).
7. **Prepare posting copy:** Generate a title, caption, and hashtags for each selected platform. Show these with the video preview. Keep copy editable before approval.
8. **Review:** The user watches the saved preview and may approve it or submit natural-language change requests for the story or subtitle position. Story changes create a new story version and rerun evaluation, narration, timing, rendering, and posting copy. Position changes rerender the current audio and subtitles only. Each revision creates a new preview; only the latest version can be approved.
9. **Export:** Approval marks the latest preview as final and makes its video and posting copy available to download and copy. The user uploads them manually.

### Run states

`queued` → `writing` → `evaluating` → `narrating` → `timing` → `rendering` → `awaiting_review` → `approved`.

Any stage can move to `failed` with a clear reason and a retry action. A revision moves an `awaiting_review` draft through only the stages affected by that request. A rejected preview remains in history but cannot be exported as approved.

## 6. Interface requirements

### Local web interface

- Configure defaults; upload, list, and remove background clips; start runs with optional overrides.
- Show run status and actionable failure reasons.
- Preview the video and posting copy; request story or subtitle-position changes; approve and download the latest version.
- Make subtitle placement visible against a portrait preview, including areas likely covered by platform controls. Position requests should support plain-language directions such as moving captions higher.

### Command line

- Start a run using saved defaults or explicit overrides and show progress, failures, and output location.
- List runs and open or identify the local review page for a draft. The web interface is the primary video-review surface; CLI and web use the same saved state.

## 7. Quality and safety checks

- **Story quality:** Use a written evaluation rubric and pass/fail reasons, not a single unexplained engagement score. The evaluator is a filter for obvious weaknesses, not a prediction of views. Log the draft, feedback, revision count, and final decision for later tuning.
- **Novelty:** Initially store compact summaries of approved stories and check new plans against recent summaries. Let the user add a plot or twist to avoid; prevent a near-duplicate from passing without a meaningful change. Whether rejected drafts should also count remains a later tuning decision.
- **Audio and captions:** Check actual duration, intelligibility, clipping, missing narration, transcription mismatch, timing gaps, and captions outside the frame. A script change invalidates downstream audio and subtitles.
- **Media:** Validate uploaded clip format and decodability before using it. A landscape or short clip must still produce a portrait video whose length matches the final story audio; a longer clip must not leave footage after the narration ends. The user is responsible for rights to uploaded clips and any voice reference audio.
- **Failures:** Keep artifacts from completed stages, show why a run stopped, and retry only the failed or affected stages. Never overwrite an approved version with an unapproved revision.

## 8. Proposed defaults to validate with the first complete video

These are product calls for the draft PRD, not decisions already made by the owner.

- Output one 9:16, 1080 × 1920 MP4 with H.264 video and AAC audio. Burn captions into the video; retain subtitle timing data locally.
- Use a high-contrast, lower-middle caption position with enough margin to avoid the bottom edge and common platform overlays. Provide position changes during review.
- Try an initial story and up to two automatic revisions. If it still fails the rubric, stop before narration and surface the flagged story.
- Treat 90 seconds as the story-audio target, with a proposed ±10-second acceptance band after narration. If audio falls outside it, adjust the script or speaking rate and regenerate. In every case, the rendered video's length follows the final audio length.
- Start with one shared video file for the three platforms; validate current platform requirements before any future publishing integration.
- Start with local Chatterbox-style narration and local `faster-whisper`-style word timing as candidates, then choose exact models and voice assets after an end-to-end quality and performance test. Do not require the experimental sample scripts as-is.
- Include no background music in phase one; mute source-clip audio so narration remains clear.

## 9. Acceptance criteria

1. With at least one valid uploaded clip, a run started from either interface can produce a playable portrait preview and platform copy using resolved and recorded inputs.
2. Each preview contains understandable narration for the approved script and synchronized short captions. Its video ends with the final story audio: longer backgrounds are trimmed, and shorter backgrounds are looped then trimmed, with only frame/codec rounding allowed.
3. Weak story drafts are revised automatically up to the configured limit; a run that cannot pass stops with its reason and no misleading finished state.
4. A story change request produces a newly evaluated script and corresponding audio, captions, video, and copy. A subtitle-position request preserves the script and narration while producing a new rendered preview.
5. Approval applies only to the latest preview. Approved output remains available for download; no phase-one action uploads it to a platform.
6. A subsequent run uses prior approved-story summaries to avoid obvious repetition and records its selected random theme and background clip.
7. Local model or rendering failures are visible and retryable without losing prior approved output.

## 10. Approaches considered

| Approach | Tradeoff | Decision |
| --- | --- | --- |
| Defined pipeline with named writing/evaluation agents and explicit media stages | Repeatable runs, bounded retries, easier recovery; less autonomous decision-making | **Chosen** for phase one. |
| Autonomous agent team choosing tools and recovery steps | More flexible, but harder to bound, reproduce, and diagnose for a single local user | Deferred; no demonstrated need. |

## 11. Future work

- Run generation on a schedule, initially targeting one video per day, on reliable always-on infrastructure.
- Connect platform accounts and publish the approved video automatically to selected platforms, with per-platform status, retry, and duplicate-post protection. Instagram professional-account eligibility and TikTok publishing approval/audit must be addressed before promising this capability. See [Meta's Instagram API documentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-3fe78620-2258-44b6-893f-42d76c7200d7) and [TikTok's Direct Post guide](https://developers.tiktok.com/docs/en/content-posting-api-get-started).
- Measure actual post performance, such as retention and completion rate, and use it to improve story selection and evaluation after enough examples exist.
- Evaluate alternative local or cloud voices, stronger alignment, multiple character voices, music, and more deliberate background selection if the initial outputs show a need.

## 12. Open validation items

- Benchmark complete narration and word timing on the owner's computer; verify acceptable generation time and naturalness with the supplied female and male references.
- Test the sample landscape clip's crop and repeated/trimmed footage in a portrait preview. Confirm caption safe margins visually.
- Calibrate the story rubric with a small set of owner-rated examples; tune the retry limit and duration tolerance from real runs.
- Confirm how long to retain rejected drafts, previews, audio, and source clips after local storage usage is known.
