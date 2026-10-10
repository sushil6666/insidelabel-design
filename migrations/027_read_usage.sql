-- 027_read_usage.sql - the read's token counts and the front's own answer (D-193).
--
-- D-193 point 1: every Gemini call's tokens (input, output, thinking), model and
-- settings are kept. A scan keeps them in scans.timings (jsonb, no column needed);
-- the review agent's draft and the table read get a column each, NULL for rows
-- before this one and for answers that made no call (a recorded one, a test).
--
-- D-193 point 2 (INSIDELABEL_READ_SPLIT_FRONT=on): the front is read in a call of its
-- own beside the back's. Its raw answer is kept here, joined or not, so a reviewer
-- sees it and a replay repeats the scan (D-092). NULL for every scan read in one call.

ALTER TABLE review_drafts ADD COLUMN usage jsonb;
ALTER TABLE review_table_reads ADD COLUMN usage jsonb;
ALTER TABLE scans ADD COLUMN model_raw_front text;
