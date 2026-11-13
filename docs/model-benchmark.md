# Local model benchmark

Date: 2026-11-13. Machine: Apple M4 Pro MacBook Pro, 24 GB RAM, macOS arm64. Python 3.11.15, FFmpeg 7.1, approximately 77 GiB free on the project volume.

## Available models and inputs

- Ollama: `qwen3:4b-instruct` and `gemma4:12b` installed. A `qwen3:4b-instruct` structured-output check returned a schema-valid, 263-word first-person workplace story and a schema-valid evaluation. The evaluator's prose incorrectly described that story as approximately 160–170 words, so deterministic word counting remains necessary. In a later real run, the 4B evaluator also passed a story claiming that the narrator buried her sister six years earlier while the sister sent emails two weeks earlier. `gemma4:12b` evaluated the same script and failed it for the explicit timeline contradiction. The app now uses Gemma for drafting and evaluation and Qwen for posting copy; these are qualitative examples, not calibrated engagement measures.
- Chatterbox TTS 0.1.7, PyTorch 2.6.0, `setuptools<81` (required by `resemble-perth`), faster-whisper 1.2.1 with cached `small.en` model.
- User supplied voice references, left untouched: `samples/female_voice_reference.mp3` (SHA-256 `2efc0418b12521134dcc23f6705ef1a5a3304ae30a7992551f4268b6c8437245`) and `samples/male_voice_reference.mp3` (SHA-256 `f427330dfc8b8aeb07b48558aa8ab2cac8c7f37743471992e026ef62bb60cc8d`). Rights and original recording provenance are not recorded.

## Initial synthesis check

The same 59-word, four-sentence workplace mystery was synthesized with each reference on Apple MPS. Whisper `small.en` transcribed the resulting WAV on CPU with `int8` and word timestamps. The test used `exaggeration=0.8`, `cfg_weight=0.5`.

| Voice | Model load | Synthesis | Raw audio | ASR | Transcript |
| --- | ---: | ---: | ---: | ---: | --- |
| Female | 8.8 s | 62.7 s | 13.5 s | 3.6 s | All source words present; punctuation differed. |
| Male | 9.8 s | 54.3 s | 14.3 s | 3.5 s | All source words present; punctuation differed. |

Both short samples are faster than the 180 WPM target and need a measured final-audio speed adjustment. The full-run result below verifies duration and rendering; listening quality and clipping inspection remain release checks.

## First complete local media run

The first 90-second target run synthesized a 263-word female narration in 278 seconds. After measured speed adjustment, the final WAV was 86.73 seconds. Whisper initially failed the script comparison because curly apostrophes were tokenized differently; a normalized comparison passed on retry using the same audio. FFmpeg looped a 1.5-second uploaded landscape clip, cropped it to 1080 × 1920, burned captions, and produced H.264/AAC MP4 in 7 seconds. `ffprobe` measured 86.733333 seconds, within one frame of the final audio. A sampled frame confirmed visible captions inside the portrait safe area.

The first story contained a timeline contradiction. A real story feedback request regenerated the story, narration, captions, video, and copy; the stronger evaluator rejected the first rewrite and accepted the second. The revised final WAV measured 89.977 seconds and its H.264/AAC portrait preview measured 90.000 seconds. A position-only request created another preview with visibly higher captions while reusing the exact revision-2 WAV and caption timing. Separately, rendering the same audio against the supplied 596-second landscape clip trimmed it to a 90.000-second portrait MP4. Those previews were later removed at the owner's request; these measurements remain historical release evidence.

The female narration's sampled peak was 0.99997 (three samples at or above 0.999). This is a very small near-clip count. The owner later listened to and accepted a newer female narration; male full-length voice quality still has not been reviewed.

## Faster 90-second narration calibration

The owner reported that the first preview sounded slow and its story did not resolve its central conflict. The revised default is 260 spoken words per minute, approximately 1.75 times the measured pace of the reviewed 222-word, 90-second sample. The story evaluator now requires an explicit resolution. On the unfinished sample it returned `resolved=false` and an ending score of 2. A local 390-word prompt produced 381 words with `gemma4:12b`; the smaller Qwen writer repeatedly returned 294 words and failed the stricter duration check. Story writing now uses Gemma, while Qwen remains for posting copy. Structured Ollama calls disable reasoning output because one longer Gemma evaluation exhausted its response in reasoning and returned empty JSON.

An intermediate replacement run used the supplied 596-second gameplay clip and a 376-word first-person story whose forger, motive, and outcome were explicit. Its evaluator returned `resolved=true`, ending 5/5. The WAV measured 90.003 seconds and the 1080 × 1920 H.264/AAC preview 90.033 seconds; a rendered frame showed the gameplay footage and readable captions. Simple whitespace word count gives about 251 WPM, approximately 1.7 times the reviewed 148 WPM preview.

The pipeline now targets audio duration from the accepted script's actual word count and requested WPM. A final 371-word run produced an 85.616-second WAV and 85.633-second portrait preview, measuring 260 WPM. Its evaluator returned `resolved=true`, ending 5/5; a frame showed the supplied gameplay clip and visible subtitles. That preview was superseded by later runs and removed at the owner's request.

## Release check, 2026-11-14

Two newer runs were approved by the owner and copied from the temporary test data folder to the default macOS application data folder after a clean server stop. A recursive comparison found no differences. The app restarted from the default location and returned both approved runs, the three platforms' posting copy, and an approved MP4 download (`200`, `video/mp4`, attachment). The owner confirmed that the newer approximately 98-second female narration sounds acceptable in voice, pace, and ending.

For the approved 90-second-target run, `ffprobe` measured 98.313583 seconds of narration and 98.333333 seconds of 1080 × 1920 H.264/AAC video. Frames sampled near the start and end showed the uploaded gameplay clip and legible subtitles inside the portrait frame. The short-clip loop and position-only revision were exercised in the earlier complete local media run above; they were not repeated after the owner requested deletion of previous runs. A browser screenshot confirmed the local page loads and shows the saved inputs, but the browser automation host could not drive the selected-run review controls. API, integration tests, and the owner's review cover those controls indirectly.
