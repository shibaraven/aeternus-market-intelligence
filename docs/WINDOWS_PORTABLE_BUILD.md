# Windows Portable Build

## Build

From a Windows command prompt with Python 3.11 available:

```bat
build.bat
```

The script creates or reuses `.venv`, installs the pinned runtime and PyInstaller requirements, runs the automated tests, and builds the one-folder application with `AeternusMarketIntelligence.spec`.

## Run

Start:

```text
dist\AeternusMarketIntelligence\AeternusMarketIntelligence.exe
```

Copy the entire `dist\AeternusMarketIntelligence` folder when moving the application to another Windows computer. The executable binds to `127.0.0.1` and opens the local web interface unless `AETERNUS_NO_BROWSER=1` is set.

Fixed Demo Mode requires no OpenAI credential. Live GPT mode reads `OPENAI_API_KEY` only from the server process environment; never place a key inside the portable folder.

## Verify

1. Start the executable.
2. Confirm `http://127.0.0.1:5000/api/health` returns HTTP 200.
3. Open **AI Research**.
4. Run `AET-DEMO` with the GPT preference cleared.
5. Confirm the seven completed tool steps, 34 evidence records, `SYNTHETIC DEMO`, `Deterministic fallback · GPT not called`, and the disclaimer.

The final judge package includes SHA256 hashes for the locally built executable or downloadable ZIP, but does not embed the full portable folder.
