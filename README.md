# Story Teller

Story Teller creates first-person English story videos on one computer. It writes and evaluates stories with selected Ollama or OpenAI models, pauses for your story approval, then synthesizes narration with Chatterbox, times captions with faster-whisper, and renders a portrait MP4 with FFmpeg. You approve the finished preview before downloading it for manual posting. Automatic publishing and scheduled generation are future work.

## Setup

Install Python 3.11, [uv](https://docs.astral.sh/uv/), and FFmpeg with `ffprobe`. The default local models require [Ollama](https://ollama.com/): the story writer and evaluator use `gemma4:12b`, and posting copy uses `qwen3:4b-instruct`. Pull both if using those defaults:

```sh
ollama pull qwen3:4b-instruct
ollama pull gemma4:12b
uv sync --python 3.11 --group dev
.venv/bin/story-teller preflight
```

Keep Ollama running while using Ollama models. Preflight checks the executables, Python version, selected Ollama models or OpenAI key, voice-reference files, free disk space, and data-folder write access. Fix any `MISSING` result before generating. On a fresh Ollama installation, start its local service with `ollama serve` in another terminal before pulling models or running preflight.

Writing, evaluation, and posting copy each have an independent model selector in the Inputs form. The defaults remain `gemma4:12b`, `gemma4:12b`, and `qwen3:4b-instruct`. Each selector also offers the other Ollama model, `gpt-6-luna` (OpenAI), and `gpt-6.1-terra` (OpenAI). Settings and run metadata retain both the provider and model. A run keeps its choices even if settings change later. Preflight checks the saved selections; a run override with an unavailable model fails visibly in the worker. The options come from `MODELS` in `service.py`; adding another provider also requires its client in `pipeline.py` and a preflight check.

For an OpenAI selection, create an ignored `.env` file in the project root containing `OPENAI_API_KEY=your-key`, or set that environment variable before starting the app. The key is read only by the worker and preflight; it is never part of settings, run inputs, or API responses. OpenAI requests send the story prompt or posting copy text to OpenAI. The app validates structured responses locally and does not store the API response at OpenAI (`store: false`).

The first speech run may need to download Chatterbox and Whisper model weights. The supplied references at `samples/female_voice_reference.mp3` and `samples/male_voice_reference.mp3` are copied to the app's managed data folder on first use. Confirm you have rights to use those voices and uploaded footage before posting.

## Generate and review

Start the server and worker in one terminal:

```sh
.venv/bin/story-teller serve
```

Open `http://127.0.0.1:8765` on the same computer. Copy background videos to `/Volumes/projects/my_projects/story_teller/background_videos/`, or upload them under **Background clips**. The folder is ignored by Git. The app discovers copied MP4, MOV, MKV, and WebM files when listing clips or starting a run. The first scan validates and copies each video into app storage and can take time for large files; the selector shows a loading message until it finishes. If you copy files while the page is open, return to the browser or choose **Refresh videos**. Adjust inputs and choose **Generate video**. You can select an existing **Background video from library**, or choose **Video for this story** to upload and use a new video for this run; the new upload is also copied into `background_videos/` for later selection. Leaving both blank randomly chooses from the clip library. Progress updates every three seconds. After evaluation, read the story in **Review** and choose **Approve story and create video**, or request a story revision. Narration, subtitles, rendering, and posting copy start only after story approval. Review the finished preview and copy, then choose **Approve video** to enable **Download approved video**. Story revisions require story approval again; subtitle-position changes reuse the narration and return to video review. The Runs dropdown uses the story title when one is available. The CLI uses the same run states; open the local review page for both approvals.

The default narration pace is 260 words per minute. Final duration follows the accepted script's word count, so a 90-second target may finish a few seconds early or late while preserving the chosen pace. The background video is trimmed to the final audio length.

To remove an old story, select it under **Previous runs** and choose **Delete selected story**. Confirming removes that run, all its revisions, and its generated files. Uploaded background clips and other runs remain available. A queued or generating run must finish or fail before it can be deleted. Back up the data folder first if you may need the story later.

The CLI uses the same local API:

```sh
.venv/bin/story-teller generate --theme 'workplace drama' --premise 'An office secret'
.venv/bin/story-teller list
.venv/bin/story-teller status --run-id RUN_ID
.venv/bin/story-teller retry --run-id RUN_ID
```

Stop the server with Ctrl+C. Only one server/worker pair can use a data folder at a time. The default data folder on macOS is `~/Library/Application Support/StoryTeller`; `serve --data-root PATH` selects another. The server and CLI must use the same data folder. A run interrupted by shutdown is recovered on startup; a failed run keeps its completed stages and can be retried after fixing the reported problem. Approved videos remain available after restart.

## Backup and recovery

Stop Story Teller before copying its data so the SQLite database and media files form a consistent snapshot. Back up the **entire** data folder, including `story_teller.sqlite3`, `clips/`, `voices/`, and `runs/`:

Back up the project's `background_videos/` folder separately if you want to preserve the copy-in library. The data folder retains managed copies for existing runs.

```sh
ditto "$HOME/Library/Application Support/StoryTeller" "$HOME/Desktop/StoryTeller-backup"
```

To restore, stop Story Teller, move the current data folder aside, then copy the backup into the default location. Use a new name for the moved folder if that name already exists:

```sh
mv "$HOME/Library/Application Support/StoryTeller" "$HOME/Library/Application Support/StoryTeller-before-restore"
ditto "$HOME/Desktop/StoryTeller-backup" "$HOME/Library/Application Support/StoryTeller"
.venv/bin/story-teller serve
```

Check the run list and an approved download before removing the moved folder or backup. For a custom `--data-root`, use that path in the commands instead. Never copy just the SQLite file while the server is running; SQLite may have uncheckpointed WAL data.

## Known limits

This is a local, single-user app. Generation needs the computer and the selected model provider available; the first speech run may download weights. If Apple MPS runs out of memory during narration, the app retries narration once on CPU, which can be much slower. Story evaluation is a quality filter, not a prediction of views. Final video duration follows measured narration and can vary from the requested target. Voice naturalness and platform overlay placement should be checked in each preview before manual posting. The supplied voice references and uploaded footage need appropriate usage rights. There is no automatic publishing or scheduled run in this phase.

## Development

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy src/story_teller
```

Pytest uses mocked model responses and blocks Python network connections, including local Ollama and cloud APIs. Running the test suite does not require a model or make paid API calls. Actual generation through the app can use OpenAI when selected.

The fixed pipeline and JSON API are described in `docs/architecture-proposal.md`; product behavior is in `docs/product-requirements.md`. The story-writing rubric is in `src/story_teller/story_prompt.txt`. `samples/` contains experimental references, not production modules. See `docs/model-benchmark.md` for measured local model performance and remaining quality checks.
