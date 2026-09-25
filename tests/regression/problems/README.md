# Reported problems, frozen as tests (D-092)

`python tools/repro.py show <id> --save NAME` writes `NAME.json` here from a real
problem report: the stored model answer and request options, replayed through
`/scan` with a 1x1 PNG (photos stay out of git; they may carry EXIF location).

`expected` starts as today's output. Edit it to what the screen **should** show;
`tests/test_problem_regressions.py` then fails until the fix lands, and keeps the
bug from coming back afterwards.
