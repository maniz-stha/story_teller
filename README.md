# Story Teller

Story Teller creates first-person English story videos on one computer. It writes and evaluates a story with Ollama, synthesizes narration with Chatterbox, times captions with faster-whisper, and renders a portrait MP4 with FFmpeg. You review each preview and manually post the approved video and copy. Automatic publishing and scheduled generation are future work.

## Setup

Install Python 3.11, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com/), and FFmpeg with `ffprobe`. The story writer and evaluator use `gemma4:12b`; posting copy uses `qwen3:4b-instruct`. Pull both before the first run:

```sh
ollama pull qwen3:4b-instruct
ollama pull gemma4:12b
uv sync --python 3.11 --group dev
.venv/bin/story-teller preflight
```

Keep Ollama running while using Story Teller. Preflight checks the executables, Python version, both Ollama models, voice-reference files, free disk space, and data-folder write access. Fix any `MISSING` result before generating. On a fresh Ollama installation, start its local service with `ollama serve` in another terminal before pulling models or running preflight.

The first speech run may need to download Chatterbox and Whisper model weights. The supplied references at `samples/female_voice_reference.mp3` and `samples/male_voice_reference.mp3` are copied to the app's managed data folder on first use. Confirm you have rights to use those voices and uploaded footage before posting.

## Generate and review

Start the server and worker in one terminal:

```sh
.venv/bin/story-teller serve
```

Open `http://127.0.0.1:8765` on the same computer. Upload at least one background clip, adjust inputs, and choose **Generate video**. The app randomly selects a named theme when Theme is Random and randomly selects an uploaded clip. The finished preview, story, and platform copy appear on the review side. You can request story or subtitle-position changes, edit posting copy, and approve the current preview. **Download approved video** returns the approved MP4; copy the platform text from the page. Story changes regenerate downstream media; position changes reuse the narration.

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

This is a local, single-user app. Generation needs the computer, Ollama, and the model files available; the first speech run may download weights. Story evaluation is a quality filter, not a prediction of views. Final video duration follows measured narration and can vary from the requested target. Voice naturalness and platform overlay placement should be checked in each preview before manual posting. The supplied voice references and uploaded footage need appropriate usage rights. There is no automatic publishing or scheduled run in this phase.

## Development

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy src/story_teller
```

The fixed pipeline and JSON API are described in `docs/architecture-proposal.md`; product behavior is in `docs/product-requirements.md`. The story-writing rubric is in `src/story_teller/story_prompt.txt`. `samples/` contains experimental references, not production modules. See `docs/model-benchmark.md` for measured local model performance and remaining quality checks.
