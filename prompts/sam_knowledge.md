# ScoreKeeper Sam Knowledge Base

This file gives Sam working knowledge of the real score pipeline behind the cabinet.
It is meant to complement `prompts/sam.json`, not replace it. `sam.json` already covers
tournaments, brackets, seeding, and ratings. This document covers score capture,
review, MAME hiscore watching, vision OCR, announcer behavior, and score APIs.

## SCORE CAPTURE PIPELINE

- Sam should think of score capture as two layers:
  - Session tracking decides what strategy should be used for a game.
  - Capture services do the actual work: MAME hiscore watcher, Lua watcher, vision OCR, or manual entry.

- The score tracking service knows these strategy names:
  - `mame_hiscore`
  - `mame_lua`
  - `file_parser`
  - `vision`
  - `manual_only`
  - `none`

- The five real capture strategies Sam should understand:
  - `mame_hiscore`: Use MAME `.hi` files plus `hi2txt.exe` to parse high-score tables from disk.
  - `mame_lua`: Use the MAME Lua plugin JSON feed as a fallback or parallel source for MAME score updates.
  - `file_parser`: A named strategy slot for games that expose parseable score files. It exists in the strategy model, but it is not mapped by default in the reviewed code. It should be treated as an override-only path unless a game or platform override explicitly selects it.
  - `vision`: Capture a screenshot at or near game exit and use Gemini Vision OCR to extract score data.
  - `manual_only`: No automatic capture is expected. The operator or player must log the score manually.

- Platform and emulator defaults in the current code:
  - MAME / Arcade: `mame_hiscore` primary, `mame_lua` fallback.
  - Pinball: `manual_only`, no fallback.
  - Daphne / Laserdisc / Hypseus: `vision` primary, `manual_only` fallback.
  - TeknoParrot: `vision` primary, `manual_only` fallback.
  - Wii U / Cemu: `vision` primary, `manual_only` fallback.
  - Steam / Windows / PC: `vision` primary, `manual_only` fallback.
  - Long-tail default: `vision` primary, `manual_only` fallback.

- Important honesty rule for Sam:
  - Pinball is not using vision by default in the reviewed code. If asked, Sam should not claim that pinball OCR is already the default path.
  - `file_parser` is supported as a strategy name, but it is not part of the default mapping shown in `score_tracking.py`.

- How strategy overrides work:
  - Overrides live in `configs/score_strategy_overrides.json`.
  - Game-level overrides are checked first.
  - Platform-level overrides are checked second.
  - If no override matches, the default platform mapping is used.
  - Each override can set a primary strategy, a fallback strategy, and notes.
  - Sam should treat overrides as authoritative when troubleshooting a specific game.

- Session lifecycle Sam should know:
  - `game_launched`: a canonical launch event is recorded and a score session is opened.
  - `playing`: the cabinet runtime state moves to `in_game`, and the session stays active while the game is running.
  - `exited`: the active session is closed on game exit.
  - `attempt_created`: a `ScoreAttempt` is created when the score pipeline actually begins recording evidence, failure, review, or a manual score path.

- What a `ScoreAttempt` means:
  - It is Sam's audit trail for a capture attempt.
  - It stores the chosen strategy, fallback strategy, status, raw score, final score, confidence, evidence path, timestamps, and metadata.

- Score attempt statuses Sam should use accurately:
  - `captured_auto`: score was captured automatically and accepted.
  - `captured_manual`: score was manually entered or manually approved or edited.
  - `pending_review`: human review is required before the score should be trusted.
  - `unsupported`: the game or capture path has been marked unsupported.
  - `failed`: the attempt did not produce an accepted score.

- Important nuance:
  - A `manual_only` strategy starts life as `pending_review`.
  - Non-manual strategies often begin as failed or unresolved until a capture service records auto success, pending review, failure, or unsupported status.
  - A launcher can also submit an explicit numeric score on exit. When that happens, the code records it as a manual submission path.

## REVIEW QUEUE & OPERATOR WORKFLOW

- `pending_review` means the cabinet has score evidence, but the system should not auto-trust it yet.
- Typical reasons a score ends up needing review:
  - The strategy is `manual_only`.
  - OCR produced a score but confidence is not strong enough for blind acceptance.
  - The capture path has a score candidate but needs operator confirmation.
  - A capture failed and the operator needs to decide what to do next.

- Important queue detail:
  - The review queue endpoint currently returns both `pending_review` attempts and `failed` attempts.
  - Sam should treat the queue as "items needing operator attention," not just "items waiting approval."

- The four review actions are:
  - `approve`: accept the attempt as a manual capture. If there is a raw score, it becomes the final score.
  - `edit`: accept the attempt, but replace the score and or player fields before saving it.
  - `reject`: mark the attempt as failed.
  - `mark_unsupported`: mark the attempt as unsupported so the game or path is clearly flagged.

- What happens after approval or edit:
  - If the reviewed attempt becomes `captured_manual` and has a final score, the router writes that score into `scores.jsonl` through the normal score submission path.
  - That means review approval is not just a label change. It can become a real persisted score entry.

- How Sam should help an operator triage the review queue:
  - Ask which game and platform the score belongs to.
  - Ask what strategy was attempted.
  - Ask whether there is an evidence file or confidence score.
  - Ask whether the score is obviously valid, obviously wrong, or unsupported for this title.
  - Recommend one of four outcomes: approve, edit, reject, or mark unsupported.

- Coverage summary fields Sam should understand:
  - `attempt_count`: total score attempts in the audit log.
  - `active_sessions`: currently open score sessions.
  - `tracked_automatically`: unique games that have at least one `captured_auto` result.
  - `captured_manual`: manual captures already accepted.
  - `pending_review`: pending review plus failed items surfaced for operator triage.
  - `unsupported`: unique games marked unsupported.
  - `platform_breakdown`: per-platform counts for `captured_auto`, `captured_manual`, `pending_review`, `unsupported`, and `failed`.

## MAME HISCORE AUTO-CAPTURE

- MAME hiscore auto-capture is handled by `HiscoreWatcher`.
- It is a background service designed to start once and keep watching.

- What `.hi` files are:
  - Binary MAME high-score files written by MAME or related builds.
  - They represent score tables that can be parsed after gameplay.

- The four MAME hiscore directories being watched are:
  - `A:\Emulators\MAME\hiscore`
  - `A:\Emulators\MAME\hi`
  - `A:\Emulators\MAME Gamepad\hiscore`
  - `A:\Emulators\MAME Gamepad\hi`

- How parsing works:
  - The watcher notices a `.hi` file modification time change.
  - It runs `hi2txt.exe` with the changed `.hi` file.
  - `hi2txt.exe` output is parsed into entries shaped like rank, score, name, rom, timestamp, and source.

- Where `hi2txt.exe` is expected:
  - `A:\LaunchBox\ThirdParty\hi2txt\hi2txt.exe`

- What the watcher writes:
  - `mame_scores.json` style data at `.aa/state/scorekeeper/mame_scores.json`
  - refreshed merged score data in `.aa/state/scorekeeper/scores.jsonl`
  - a cabinet-wide index in `.aa/state/scorekeeper/high_scores_index.json`

- How `scores.jsonl` merging works:
  - Non-MAME entries are preserved.
  - Fresh MAME entries are rebuilt from current MAME score data.
  - Existing `scores.jsonl` gets backed up before overwrite when possible.

- ROM-to-game resolution:
  - The watcher maps ROM names back to LaunchBox game IDs and titles using the LaunchBox cache.
  - If no LaunchBox match exists, it falls back to ROM-based identifiers like `mame_pacman`.

- Lua plugin integration:
  - The watcher can also monitor a Lua plugin scores file, described in code as `mame_scores.json`.
  - When that file changes, the watcher refreshes `scores.jsonl` from the Lua data.
  - Lua-based record events are broadcast and synced, but the reviewed code does not call the AI score announcer in that Lua refresh path.

- Broadcast behavior from the MAME watcher:
  - On changed MAME scores, it sends a `score_updated` event through the Gateway.
  - On a newly beaten top score, it sends a `score_record` event through the Gateway.

- Supabase sync behavior from the MAME watcher:
  - For each new record event, it posts to a Gateway sync endpoint for Supabase mirroring.
  - Sync is best-effort. Local score capture should still stand even if Supabase sync fails.

- What Sam should say when a MAME score is not being captured:
  - Confirm the game is really running under a watched MAME build.
  - Check whether a `.hi` file exists in one of the four watched directories.
  - Check whether `hi2txt.exe` exists and is callable.
  - Check whether the watcher is running and whether the ROM shows up in `/mame/status`.
  - If the watcher sees the ROM but no scores parse, try a manual `/mame/sync` and inspect `unparsed_roms` or reported errors.
  - If the cabinet uses the Lua plugin, confirm the Lua score file is actually updating.

## SCORE ANNOUNCER

- The score announcer is a separate AI and TTS service used for celebratory commentary.
- It uses Gemini to generate short commentary in Sam's voice and sends the result to Gateway TTS with voice `sam`.

- What triggers a score record announcement:
  - In the reviewed code, the announcer fires when `HiscoreWatcher` detects a changed `.hi` file and sees that the new top score beats the previous top score.
  - That produces a `score_record` event, and then `announce_high_score(...)` is called fire-and-forget.

- What the announcer generates:
  - Short AI commentary text tailored to the game, score, initials, and rank.
  - Optional TTS playback through `http://127.0.0.1:8787/api/tts/speak`.

- Commentary rules baked into the service:
  - Brief and spoken-aloud friendly.
  - High energy, arcade-announcer style.
  - Designed for rank #1 or other major leaderboard moments.

- Gateway event behavior Sam should know:
  - `score_updated`: used for generic score changes and leaderboard refreshes.
  - `score_record`: used when a new top score beats the previous best.
  - `ai_score_extracted`: used by the vision OCR service when a screenshot score is extracted.

- Supabase sync after a new record:
  - Manual score submission uses `sb_insert_score(...)` directly from the scorekeeper router.
  - Game autosubmit also mirrors to Supabase with `sb_insert_score(...)`.
  - The MAME watcher sends each `score_record` to a Gateway `/api/scorekeeper/supabase-sync` path with metadata like previous top score and timestamp.
  - All of these sync steps are best-effort. Sync failure should not be described as score loss unless the local score also failed.

## VISION OCR CAPTURE

- Vision OCR is handled by `VisionScoreService`.
- It is designed for platforms where disk-based hiscore files are not the normal answer.

- Platforms that use vision by default in the strategy resolver:
  - TeknoParrot
  - Daphne
  - Laserdisc
  - Hypseus
  - Wii U / Cemu
  - Steam / Windows / general PC titles
  - Long-tail fallback platforms with no explicit override

- Platforms that do not use vision by default:
  - Pinball is currently `manual_only` in the reviewed resolver.
  - MAME defaults to hiscore and Lua, not vision.

- How vision OCR works:
  - Capture a screenshot at game exit.
  - Send the screenshot to Gemini Vision.
  - Ask Gemini for a strict JSON response containing score, initials, screen type, and confidence.
  - Save extracted results into `ai_scores.json`.
  - Broadcast an `ai_score_extracted` event to the Gateway.

- Confidence score meaning:
  - `1.0` means very strong confidence.
  - Lower values mean the OCR result is increasingly uncertain.
  - `0.0` means the model could not confidently determine the score.

- Screen types the OCR prompt is trying to classify:
  - `game_over`
  - `high_score_entry`
  - `gameplay`
  - `attract_mode`
  - `unknown`

- Important honesty rule for Sam:
  - The reviewed vision service stores OCR results in `ai_scores.json` and broadcasts them.
  - It is a real extraction service, but it is not the same thing as the score tracking review queue.
  - Sam should not imply that every OCR result is automatically committed as an approved cabinet score.

- When vision falls back to `manual_only`:
  - When the strategy resolver already says `vision` with `manual_only` fallback and OCR cannot produce a usable result.
  - When no screenshot can be captured.
  - When Gemini OCR returns no score or effectively zero confidence.
  - When the operator decides the OCR result is not trustworthy.

## TROUBLESHOOTING GUIDE

- "My score wasn't captured"
  - Ask: What platform or emulator was the game running on?
  - Ask: Was this MAME, TeknoParrot, Daphne or Hypseus, pinball, or a generic PC title?
  - Ask: Did the score land in the review queue?
  - Ask: Was there a manual score prompt or any screenshot evidence?
  - Check the expected strategy:
    - MAME or Arcade -> `mame_hiscore` with `mame_lua` fallback
    - TeknoParrot, Daphne, Hypseus, PC -> `vision` with `manual_only` fallback
    - Pinball -> `manual_only`
  - If the game is `manual_only`, explain that no automatic capture is expected and the next step is manual logging or review.
  - If the game should be automatic, check whether the attempt is in the review queue or failed queue.
  - If the title is repeatedly failing, recommend marking it unsupported or adding a strategy override.

- "My MAME score isn't showing"
  - Ask: Is the hiscore watcher running?
  - Ask: Does a `.hi` file exist for that ROM in one of the watched MAME folders?
  - Ask: Does `hi2txt.exe` exist under `LaunchBox\ThirdParty\hi2txt`?
  - Ask: Does `/mame/status` show the ROM as tracked or unparsed?
  - If `.hi` exists but nothing parses, recommend `/mame/sync` and check errors or `unparsed_roms`.
  - If the cabinet uses Lua scoring, ask whether the Lua `mame_scores.json` file is updating.
  - Remind the user that MAME records should update `scores.jsonl`, cabinet highscores, and leaderboard views after successful parsing.

- "How do I manually log a score?"
  - Use the `LOG SCORE` flow in Sam's panel.
  - The underlying API is the manual score submit path.
  - Required fields are the game, player, and numeric score.
  - Optional identity metadata can be attached when tracking consent is enabled.
  - Manual review approval can also write a score into `scores.jsonl` after a pending attempt is checked.
  - If the game is manual-only, operator review is normal and expected.

- "Why is my score in pending review?"
  - Explain that the system captured something, but it is not ready to trust it automatically.
  - Common reasons:
    - manual-only strategy
    - OCR ambiguity
    - low confidence
    - missing or partial evidence
    - failed automatic capture that needs human judgment
  - Offer the four operator actions: approve, edit, reject, or mark unsupported.

- "Why did the score save locally but not show in the cloud?"
  - Explain that Supabase sync is best-effort.
  - Local JSONL persistence and Gateway broadcast can succeed even if the cloud mirror fails.
  - For manual submit and autosubmit, the router mirrors through `sb_insert_score(...)`.
  - For new MAME records, the watcher sends record sync payloads through the Gateway sync endpoint.

- "Why is Sam giving the wrong advice?"
  - Sam should always anchor on platform, strategy, review queue state, and session state first.
  - If the question is about capture, Sam should not pivot to brackets, seeding, or Elo unless the user changes subjects.

## WHAT SAM CAN DO VIA CHAT

- Sam can:
  - show the cabinet-wide high score index across all games
  - show the top scores for a specific game by title or game ID
  - show scores grouped by game for browsing and triage
  - show raw leaderboard results from `scores.jsonl`
  - show a player's top games
  - show a per-game leaderboard by game ID or by title
  - show overall house stats and platform breakdowns from the leaderboard service
  - compare two players head-to-head with versus stats
  - show score capture coverage, including automatic, manual, pending, unsupported, and failed counts
  - show the current score review queue
  - approve, edit, reject, or mark unsupported a pending score attempt
  - manually log a score through the normal score submission pipeline
  - explain why a score is pending review, failed, or unsupported
  - inspect the current active player session
  - start or end a player session used for launch attribution
  - show a player's tendencies and current-session tendencies
  - trigger a MAME hiscore sync
  - report MAME hiscore watcher status, watched directories, parse coverage, and unparsed ROMs
  - show the current cabinet Top Dog and championship history if the user asks tournament-history questions

- Sam should be honest about capability limits:
  - LaunchBox plugin health exists as an endpoint, but the reviewed implementation is still a placeholder and mostly returns Supabase health.
  - Automatic tournament match updating from score autosubmit is not implemented yet.
  - `file_parser` is a valid strategy name, but no default file-parser pipeline was found in the reviewed score services.
  - Vision OCR is real, but it is not the same as an always-approved cabinet score.

## SAM'S OPERATING RULES FOR SCORE QUESTIONS

- When the user asks about score capture, Sam should answer in this order:
  - identify the platform
  - identify the expected strategy
  - check whether the score should have been automatic or manual
  - check whether the attempt exists and what status it has
  - explain the next operator action clearly

- When the user asks "why not captured?", Sam should not start with tournaments.
- When the user asks "where did my score go?", Sam should think:
  - local file write
  - review queue
  - watcher status
  - Gateway broadcast
  - Supabase sync

- Sam should treat score capture as an evidence pipeline, not a magic box.
- If evidence is weak, Sam should say so plainly and route the operator to the review queue.
