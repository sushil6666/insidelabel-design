# InsideLabel: personal data map (for the DPDP review)

Prepared 2026-09-28 from the code on `main` (commit 0c15d93) and the server setup in `DEPLOY.md`.
It lists every piece of personal data the app handles, where it is kept, who can see it and when
it is deleted, then the open questions for the reviewer. Read it with the draft privacy page,
`web/site/privacy.html` (https://insidelabel.ai/privacy).

Sources read first-hand for this map: the Digital Personal Data Protection Act, 2023 (MeitY copy
of the Gazette text); the Gemini API Additional Terms of Service (ai.google.dev, last updated
2026-04-28). The DPDP Rules, 2025 (notified 14 November 2025) were **not** read first-hand: the
MeitY page only loads in a browser. Where this map mentions the Rules, it relies on the
Government's own summary (PIB, "DPDP Rules, 2025 Notified", 17 November 2025). The reviewer
should check those points against the Rules text.

## 1. What the service is

An invite-only beta web app (a PWA) for adults in India who shop for packaged food. A user
photographs a pack; the app reads the ingredient list and says whether any listed ingredient
matches the foods the household avoids (allergens) and what additives and sugars are listed.
No account, name, phone number or email is asked for. Operator: Sushil (sole founder).
Hosting: one Google Cloud virtual machine in Mumbai (asia-south1).

## 2. The data, one row each

| # | Data | Why | Where kept | Who can see it | When deleted today |
|---|---|---|---|---|---|
| 1 | **Install id**: a random id the browser makes on first use (`users.id`) | Ties a device's scans, reports and feedback together; rate limits | Server database; the phone (`localStorage`) | Operator | 12 months after the device was last seen (D-128) |
| 2 | **Invite code and its label**: the code a tester joined with (`invite_devices`); the operator's own label for the code (`invites.label`) | Invite-only beta; knowing which tester sent what | Server database | Operator only; the app never shows the label | With the install id (D-128). Labels are codes (T01), no names |
| 3 | **Terms agreement**: install id, terms version, time (`agreements`) | Record that the user agreed | Server database | Operator | With the install id (D-128) |
| 4 | **Pack photos** (front and back of a food pack; since D-130 also a photo or screenshot of a screen showing one, such as a shop listing) and the barcode | Reading the label | Server disk (`/var/lib/insidelabel/media`); sent to Google (row 10) | Operator; reviewers of the catalogue; Google as processor | **30 days** after the scan, by a daily job (`retention.py`, D-080, D-098), unless: the user reported a problem with that scan, sent the pack to us, a review of it is open, or the photo became the reviewed catalogue record of that pack |
| 5 | **Scan record**: time, result, the model's reading of the label, timings, and the request (`scans`) | Showing the result; replaying a scan to fix a bug (D-092) | Server database | Operator | The link to the install id is removed after 30 days (D-128); what the label said is kept |
| 6 | **Household profiles sent with each scan**: for each person, an age band (baby, toddler, kid, young, adult, older) and the foods they avoid (for example milk). Stored inside the scan record's request (`scans.request`) | Checking the pack for those foods; the children's view | The phone keeps the full profile; the server keeps the age band and avoid list per scan | Operator | Removed from the scan after 30 days (D-128), unless the scan is held for a report, and never kept past 12 months |
| 7 | **Nicknames and the parental consent tick** | Showing "Aarav" instead of "your child" | **Phone only.** Never sent (`profilesForServer()` sends ref, age and avoid list only, D-074) | Nobody but the phone's user | When the user clears the app's site data |
| 7a | **Shop list** (D-130): products checked from a screen, with the ingredient list and allergen line as read | Scanning the pack in the shop; when "Scan it now" is used, that one list is sent with the pack's scan (`screen_pack`, no names) and kept in that scan's request (row 5) | **Phone only**, except the one list sent with a scan | Nobody but the phone's user | When the pack is scanned, "Remove", or "Delete my data" |
| 8 | **Feedback**: rating and free text (`feedback`) | Beta feedback | Server database | Operator | 12 months (D-128) |
| 9 | **Problem reports**: the user's comment, the app's recent trail (screens, API calls, errors; no names, no query strings, no label text), the browser's user agent, language, screen size and network type (`problem_reports`) | Fixing bugs; the user sees exactly what is sent before sending | Server database | Operator | 12 months (D-128) |
| 10 | **Photos sent to Google** for reading: Gemini API (reads the ingredient list) and Cloud Vision API (reads the text again as a check). The review agents send catalogue photos to Gemini again to draft a review | Reading the label (AI reads, rules judge, D-004) | Google | Google as processor | Per Google's terms (section 4, point 1) |
| 11 | **IP address** | Rate limiting | **Memory only**, for the rate-limit windows (at most one day). No access log in Caddy or uvicorn, on purpose | Nobody | On restart, or when the window passes |
| 11a | **Days an install scanned**: install id, date, number of scans (`device_days`) | The beta's week-4 retention measure (D-055) after scans are unlinked | Server database | Operator | With the install id (D-128) |
| 12 | **Backups** of the database | Recovery | Server disk, daily dump kept 14 days (`backup.sh`); disk snapshot daily, kept 7 days, stored in Mumbai (DEPLOY.md) | Operator | 14 days (dumps); 7 days (snapshots, which also hold the photos) |
| 13 | **Email** to `connect@insidelabel.ai` | Questions and requests | Zoho Mail | Operator | No rule yet |

Not collected: name, phone number, email (unless the user writes to us), location, contacts,
advertising ids. No analytics or advertising scripts; the pages load no third-party fonts or
scripts. No tracking across sites. No sale or sharing with other companies beyond the
processors above.

Unused: the `user_profiles` table (from the first schema) exists but nothing writes to it
(0 rows). Profiles reach the server only inside each scan's request (row 6).

## 3. Who processes data for us

| Processor | What it receives | Where | Terms |
|---|---|---|---|
| Google Cloud (Compute Engine, disk, snapshots) | Everything on the server | Mumbai (asia-south1) | Google Cloud terms and data processing terms (to be confirmed by the reviewer) |
| Google Gemini API | Pack photos; the prompt | Google says data "may be stored transiently or cached in any country in which Google or its agents maintain facilities" | Gemini API Additional Terms (section 4, point 1) |
| Google Cloud Vision API | Pack photos (the back) | Google | Google Cloud terms |
| Zoho Mail | Emails to `connect@insidelabel.ai` | Zoho (India, MX `mx.zoho.in`) | Zoho terms |

## 4. Points for the reviewer

These are the places where what the app does today may fall short of the Act, or where a
choice is needed. Section numbers are from the Act.

1. **Gemini: paid quota, confirmed by Sushil 2026-09-28 (D-129).** The Gemini terms say that
   on paid quota Google "doesn't use your prompts ... or responses to improve our products",
   processes them under its Data Processing Addendum, and logs them "for a limited period of time,
   solely for detecting and preventing violations of the Prohibited Use Policy" and legal
   disclosures. (On unpaid quota Google may use them to improve its products and "human
   reviewers may read" them.) The privacy page says paid.
2. **Gemini's age clause.** The same terms say the API may not be used in an app "that is
   directed towards or is likely to be accessed by individuals under the age of 18". The privacy
   page says the app is for adults; children appear only as profiles an adult sets up. The reviewer
   should say whether that is enough.
3. **Children's data (s.9).** A child's age band and avoid list are personal data of a child
   ("child" = under 18, s.2(f)). s.9(1) requires "verifiable consent of the parent" "in such
   manner as may be prescribed". Today the app asks the adult to tick "I am this child's parent
   or guardian. I agree to InsideLabel using this age band and avoid list to check labels for
   them." It keeps that tick **on the phone only**; the server has no consent record.
   Questions: is a tick enough under the Rules; must the server keep the record; would
   storing less (see 5) change the answer. s.9(3), no tracking or behavioural monitoring of
   children: the app builds no profile of a child over time; each scan is checked on its own.
4. **Invite labels:** now codes only (T01); the tool no longer suggests names (D-128). Labels
   already made should be checked for names.
5. **Deletion rules (s.8(7)), decided by Sushil as D-128 and built:** scans are unlinked
   from the install id, and the household profiles removed, after 30 days; what the label said
   is kept for good. Feedback and problem reports: 12 months. Install ids, invite links,
   agreements and day counts: 12 months after the device was last seen. Photos: still 30 days.
   Sushil wants to keep photos in archive storage instead; the question for the reviewer is
   whether an unlinked pack photo that shows a hand or a face is still personal data. s.8(8)
   lets the Rules set the period for "no longer served"; check whether they do for this class.
6. **Rights: access, correction, erasure (s.11, s.12) and grievances (s.13): built as D-129.**
   "Your data" in the app shows the install id and has "Delete my data" (`POST /forget`), which
   erases every row for that install id and its photos, except a photo that became a catalogue
   version's evidence (the pack's record, with no link to the person). Access and correction
   requests go by email to `connect@insidelabel.ai`, quoting the id; the page promises an answer
   within 90 days (the PIB summary's limit). Question for the reviewer: is keeping a catalogue
   photo after an erasure request acceptable, given it is kept for the catalogue, not about the
   person?
7. **Contact (s.8(9)) and the notice (s.5).** The notice must name the data and purpose, how to
   use the rights and how to complain to the Data Protection Board, and (s.5(3)) be available
   in English or a language of the Eighth Schedule. Contact: `connect@insidelabel.ai`. The
   page now names the Board; it doesn't yet offer other languages.
8. **Breach notice (s.8(6)).** No written plan yet for telling the Board and affected users.
   With no email or phone numbers kept, users could only be told in the app. The reviewer
   should say what is enough.
9. **Photos may show more than the pack**: a hand, a face, a receipt. Photos are read only for
   the label and deleted at 30 days (row 4). The privacy page could ask users to photograph
   only the pack.
10. **Phased start.** The PIB summary says the Rules give "an eighteen-month period for phased
    compliance". The reviewer should say which duties already apply to a small beta and which
    start later.
11. **Screenshots of shop listings (D-130).** Users may now send a photo or screenshot of a
    retailer's listing (Amazon, Blinkit and similar) to check a product before shopping. We don't
    scrape or copy listings (D-088): the user brings the image for their own check, it is read
    once, never added to the catalogue, and deleted at 30 days like any scan photo. A screenshot
    can also show the user's own account, address or order details. The reviewer should say
    whether this is acceptable as it stands, or whether the privacy page should ask users to crop
    to the ingredient list.
