-- Crash reports become work items for the automated triage runner.
--
-- `status` tracks the report through the pipeline (new -> analyzing -> mr_open ->
-- done, or failed). The default 'new' also stamps every existing, never-looked-at
-- row, which is correct: nothing has processed them.
--
-- `stacktrace_hash` is a sha256 over the raw stacktrace text, computed on insert.
-- It exists so the runner can recognise the same crash arriving twice and skip a
-- second fix attempt without comparing LONGTEXT columns. NULL for manual
-- diagnostics reports, which carry no stacktrace.
--
-- Mirrored by the SHOW COLUMNS guard in services/music_manager/routers/diagnostics.py.
ALTER TABLE crash_reports
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'new' AFTER ring_buffer_text;
ALTER TABLE crash_reports
    ADD COLUMN IF NOT EXISTS stacktrace_hash CHAR(64) NULL AFTER status;
