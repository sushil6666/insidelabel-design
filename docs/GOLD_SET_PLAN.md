# Growing the gold set from 6 to 20 labels (2026-09-30)

The gold set size gate needs 20 hand-transcribed labels, a third in bad conditions
(`tools/release_check.py`, blueprint §15). There are 6. Most of what the beta still
measures (ingredient match, D-137; false contradictions; nutrition numbers, D-133) is only
as meaningful as this set. This plan uses packs already photographed and published on
insidelabel.ai, so no new shooting is needed, but it keeps the RUNBOOK's one rule.

## The rule this plan keeps

`tools/new_gold.py` and `RUNBOOK.md` step 4: **gold is transcribed blind from the photo,
never made by correcting model output.** A published catalogue version is exactly that
(a Gemini draft that a person checked), so it would agree with the model by construction.
So from the catalogue we take **only the photos**, never the ingredient record.

## Steps

| # | Who | What | Cost |
|---|---|---|---|
| 1 | Sushil (server) | List the published packs with their photos (query below) | free |
| 2 | Sushil, Claude | Choose 14 (below) | free |
| 3 | Sushil (server, then laptop) | Copy those photos to `photos/<id>-back.jpg` / `-front.jpg` | free |
| 4 | Claude | `python tools/new_gold.py --id <id>` for each, then transcribe from the photo only, without opening the catalogue record or any prediction | free |
| 5 | Sushil | Check each gold file against its photo (as with the four nutrition tables) | free |
| 6 | Sushil says "run the gold set" | One read of all 20 with the current prompt (and D-137's prompt line, if accepted), written to a scratch path first | about Rs 10 (20 Gemini reads at about 50 paise) plus 20 Cloud Vision reads |
| 7 | Claude | `python tools/release_check.py` against the new predictions; report what moved | free |

## 1. The list (run on the server)

```bash
sudo -u insidelabel psql -d insidelabel -c "
SELECT pv.id AS version, p.barcode, b.name AS brand, p.name, p.variant, c.code AS category,
       pv.verified_by, pv.verified_at::date AS published,
       coalesce(i.label, 'no invite (admin or unlinked)') AS taken_by,
       pv.back_image_key, pv.front_image_key
  FROM product_versions pv
  JOIN products p ON p.id = pv.product_id
  LEFT JOIN brands b ON b.id = p.brand_id
  LEFT JOIN categories c ON c.id = p.category_id
  LEFT JOIN LATERAL (SELECT s.user_id FROM scans s
                      WHERE s.back_image_key = pv.back_image_key
                      ORDER BY s.created_at LIMIT 1) s ON true
  LEFT JOIN invite_devices d ON d.user_id = s.user_id
  LEFT JOIN invites i ON i.code = d.code
 WHERE pv.status = 'published' AND pv.is_current
 ORDER BY pv.verified_at;"
```

Checked against all 18 migrations on a scratch database (2026-09-30). `taken_by` is the
invite label of the phone that first sent the back photo. The retention job keeps every
photo on a version that isn't rejected, so all of these are still on disk.

## 2. Choosing the 14

- **Only photos Sushil took himself** for now. A tester's photo may show a hand or a face;
  D-128 left that question for the DPDP reviewer, and the gold photos leave the server.
  (`photos/` is not tracked by git; they stay on the laptop.)
- **3 to 4 with a front claim** ("no added sugar", "no preservatives", "made with real
  X"): without them the false-contradiction gate stays unmeasured.
- **At least 7 in bad conditions** across the 20 (a third): shop lighting, glare on foil,
  a curved pouch. Photos from the supermarket runs are the real thing. The six today are
  mostly clean, so the new 14 should carry most of the bad third.
- Cover the RUNBOOK step 1 table: foil packets, pouches, noodles with "Tastemaker:",
  a short dairy or drink list, one or two very simple packs, biscuits (D-058's kids'
  biscuits count twice: they are also the catalogue's seed).
- **Never** swap a photo because the model reads it badly: that is the measurement.

Give each an id as the RUNBOOK says (`brand-product-variant`, lowercase, hyphens).

## 3. Copying the photos

A key is a content hash with its extension; the file is `media/<first 2 characters>/<key>`.
On the server, with the keys from step 1 in `/tmp/gold-keys.txt` (one per line):

```bash
cd /var/lib/insidelabel/media
sudo tar czf /tmp/gold-photos.tgz $(sed 's|^\(..\)|\1/\1|' /tmp/gold-keys.txt)
```

On the laptop:

```bash
gcloud compute scp insidelabel-1:/tmp/gold-photos.tgz . --zone=asia-south1-a
```

Then rename each file to `photos/<id>-back.jpg` / `photos/<id>-front.jpg`, and delete
`/tmp/gold-photos.tgz` and `/tmp/gold-keys.txt` on the server.

## Open for Sushil

- Is a tester's photo allowed into the gold set, or only his own until the DPDP answer?
- D-137 (how gold splits an ingredient list) is best settled before step 4, so the 14 new
  files are transcribed one way from the start.
