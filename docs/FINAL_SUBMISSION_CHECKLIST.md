# Final Submission Checklist

This checklist records observed state. Do not change an item to `[x]` until the action was executed and verified.

## Repository and documentation

- [x] Public repository URL is documented: `https://github.com/shibaraven/aeternus-market-intelligence`.
- [ ] GitHub default branch opens directly to the final Build Week version.
- [x] README explains purpose, installation, Fixed Demo, GPT-5.6, Codex, tests, limitations, and disclaimer.
- [x] Judge instructions are in `docs/JUDGE_TESTING_GUIDE.md`.
- [x] Architecture and validation documentation are present.
- [x] Pre-Build-Week features and Build Week additions are distinguished.

## Product validation

- [x] Automated suite passes: 18 tests in the latest source validation.
- [x] Python compilation, dependency check, and inline JavaScript parsing pass.
- [x] Fixed Demo Mode completes without a credential.
- [x] Fixed Demo shows `AET-DEMO`, `SYNTHETIC DEMO`, seven completed tools, 34 evidence records, 2026-06-30, and `GPT not called`.
- [x] Windows portable application builds, starts, and completes the Fixed Demo workflow.
- [x] Secret scan passes for tracked submission content.
- [x] One genuine GPT-5.6 Sol Responses API run passes structured-output and numerical-traceability validation.
- [x] `docs/LIVE_GPT_VALIDATION.md` contains a PASS result and actual returned model ID.

## Demo media

- [x] Reproducible 1920×1080 Playwright recorder exists and fails closed without a valid live report.
- [x] Local English voiceover WAV exists and is 2:20.795 with normalized audible level.
- [x] Matching English SRT exists.
- [x] Raw recording contains verified live GPT, Fixed Demo, research output, and engineering scenes.
- [x] Final MP4 is H.264/AAC, 1920×1080, yuv420p, fast-start, and under 180 seconds.
- [x] `submission-artifacts/VIDEO_VALIDATION.txt` contains exact ffprobe output and all PASS checks.
- [x] Complete final video was inspected at five-second intervals for readability, scene timing, subtitles, black frames, audio, and visible private information.

## Devpost assets

- [x] `01-cover.png` is 1800×1200 and below 5 MB.
- [x] `02-ai-research-input.png` is 1800×1200 and below 5 MB.
- [x] `03-live-gpt-tool-timeline.png` is generated only from a successfully validated live report.
- [x] `04-evidence-report.png` is 1800×1200 and below 5 MB.
- [x] `05-backtest-comparison.png` is 1800×1200 and below 5 MB.
- [x] `06-architecture.png` is 1800×1200 and below 5 MB.
- [x] Copy-paste Devpost content is in `docs/DEVPOST_SUBMISSION.md`.
- [x] Copy-paste YouTube content is in `docs/YOUTUBE_METADATA.md`.

## Judge package and clean clone

- [x] Current patched worktree passes a fresh-venv clean-snapshot rehearsal, including npm recorder install, tests, source Fixed Demo, fresh PyInstaller build, packaged Fixed Demo, and secret scan.
- [x] Judge package contains all required documents, the successful live validation, a sanitized sample report, six gallery images, portable-build instructions, and SHA256 hashes.
- [x] Judge ZIP is below 35 MB and contains no secret, `.env`, database, browser profile, cache, or unlicensed dataset.
- [x] Final clean clone installs from documented commands.
- [x] Final clean clone passes tests, source startup, Fixed Demo, judge workflow, and portable-build validation.
- [x] Final validation report contains the final clean-clone outputs.

## Git and publishing

- [x] Appropriate source, script, documentation, test, and gallery changes are committed to `build-week-2026`.
- [x] Large video, audio, raw recording, and judge ZIP remain ignored and uncommitted.
- [x] `build-week-2026` is pushed without force-pushing unrelated history.
- [x] `pre-build-week-2026` tag is created from the preserved pre-Build-Week main commit and pushed.
- [ ] `build-week-2026` is merged into `main` only after every technical gate passes.
- [ ] `main` is pushed and remains the GitHub default branch.
- [ ] YouTube upload metadata, thumbnail, and Public visibility are prepared.
- [ ] User explicitly confirms the irreversible YouTube **Publish** action.
- [ ] Published YouTube URL is added to Devpost.
- [ ] Devpost story, repository, judge instructions, gallery, and optional package are prepared.
- [ ] User explicitly confirms the irreversible Devpost **Submit Project** action.
- [ ] Run `/feedback` in this Codex task and copy the real Session ID into Devpost; do not fabricate one.
