# InsideLabel on Google Play: the first release

Prepared 2026-10-01 on branch `play-wrap` (D-148, D-149). The Play app is the Trusted Web Activity
(TWA) of https://insidelabel.ai/app/ that D-010 planned: Chrome shows the live site full screen, with
no address bar once the site and the app vouch for each other (section 3). Nothing in the app is
separate from the site: every change still reaches users through `main` and `deploy/update.sh`.

**Fixed facts (never change):** package `ai.insidelabel.app.f` (D-149, permanent after the first
upload); host `insidelabel.ai` only (D-114); start and scope `/app/`; name and launcher name
"InsideLabel"; colours from `web/manifest.webmanifest`; icon `web/icon-512.png`, maskable
`web/icon-maskable-512.png`; portrait. Default listing language English (United Kingdom), en-GB.
Developer email isushilb@gmail.com. Privacy policy https://insidelabel.ai/privacy.html. No ads, no
payments, no Play Billing, no notifications, no location (D-148).

**Who does what.** The build session wrote `android/`, the asset links route and this file. Sushil
makes the upload key, builds the signed bundle on his laptop, uploads it and fills Play Console. No
key, password or Google key is ever in the repo (D-012); `tests/test_android_project.py` fails if a
`.jks`, `.keystore`, `.p12`, `.pfx`, `.pk8` or `keystore.properties` is ever tracked.

Contents: 1. What is in `android/` · 2. Build on the laptop · 3. Asset links · 4. Play Console, in
order · 5. App content answers · 6. Store listing · 7. Phone checklist · 8. Questions for Sushil

---

## 1. What is in `android/`

Generated on 2026-10-01 with `@bubblewrap/core` 1.25.0 (the code `bubblewrap init` runs, without
its prompts) from `web/manifest.webmanifest`.

| Setting | Value | Where it comes from |
|---|---|---|
| Package | `ai.insidelabel.app.f` | D-149 |
| Start URL, scope | `https://insidelabel.ai/app/` | the web manifest (`start_url`, `scope`) |
| Name, launcher name | InsideLabel | the web manifest |
| Icon, maskable icon | `icon-512.png`, `icon-maskable-512.png` | the web manifest; Bubblewrap would have picked the SVGs, so these are set by hand |
| Status bar, navigation bar, splash | `#FBF9EE` | the web manifest's `theme_color` and `background_color` |
| The same in dark mode | `#193043` | `web/app.css`, the dark `--bg` (the manifest has no dark colour) |
| Orientation | portrait | the web manifest |
| versionCode, versionName | 1, "1" | first upload |
| targetSdk, compileSdk | 36 | Play's rule, below |
| minSdk | 21 (Android 5.0) | Bubblewrap's default |
| If Chrome can't run a TWA | custom tabs | Bubblewrap's `fallbackType` |
| Notifications, location, billing | off | D-148 |
| Permissions the app asks for | none | the camera prompt is Chrome's, for the site, as on the web |
| Upload key (for `bubblewrap build`) | `../../insidelabel-keys/insidelabel-upload.jks`, alias `upload` | outside the repo: from `~/insidelabel/android` it is `~/insidelabel-keys/` |

**Play's target API level**, read 2026-10-01 from
https://developer.android.com/google/play/requirements/target-sdk (page last updated 2026-09-16):
"Starting August 31 2026: New apps and app updates must target Android 16 (API level 36) or higher
to be submitted to Google Play". Bubblewrap 1.25.0's template targets 36.

**Not proved here: the build.** This cloud session's network policy refuses `dl.google.com`, and
`maven.google.com` redirects there, so neither the Android SDK nor the Android Gradle Plugin can be
downloaded. Gradle 8.11.1 itself ran (on JDK 21) and stopped at
`com.android.tools.build:gradle:8.9.1` with "Received status code 403". The first real build is the
one in section 2. To let a later cloud session build it, allow `dl.google.com` in the environment's
network settings.

**To change a setting later:** edit `android/twa-manifest.json`, then in `android/` run
`bubblewrap update` (it also raises versionCode by 1, which every new upload needs), commit what it
writes, build, upload. `manifest-checksum.txt` records which `twa-manifest.json` the project was made
from; `tests/test_android_project.py` checks it.

---

## 2. Build on the laptop (WSL, Ubuntu 24.04)

All of this runs in Sushil's laptop terminal, never on the server. Bubblewrap installs its own JDK
and Android SDK under `~/.bubblewrap/`.

**Download, once:** the JDK 17 (Temurin 17.0.11) about 190 MB, Android command line tools about
85 MB, build tools 36.1.0, the Android 36 platform, Gradle 8.11.1 (about 130 MB) and the Android
Gradle Plugin with its libraries. These sizes are estimates: about 1 GB to download and about 3 GB of
disk, mostly on the first build. Later builds reuse it.

### 2.1 Install (once)

```bash
node --version                      # needs 18 or newer
# if missing or older:
sudo apt-get update && sudo apt-get install -y nodejs npm
sudo npm install -g @bubblewrap/cli@1.25.0     # the version that generated android/
bubblewrap doctor
```

`bubblewrap doctor` asks two questions on its first run. Answer **Yes** to "Do you want Bubblewrap
to install the JDK" and **Yes** to installing the Android SDK, then accept the Android SDK licence. It
ends with "Your jdkpath and androidSdkPath are valid."

### 2.2 The upload key (once; never in the repo)

```bash
mkdir -p ~/insidelabel-keys && chmod 700 ~/insidelabel-keys
KEYTOOL=$(ls -d ~/.bubblewrap/jdk/jdk-17*)/bin/keytool
$KEYTOOL -genkeypair -v -keystore ~/insidelabel-keys/insidelabel-upload.jks \
  -alias upload -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=InsideLabel, O=InsideLabel, C=IN"
```

It asks for a password twice. Use a long new one, kept only in a password manager. (The file is
PKCS12, so the key password is the same as the store password; `bubblewrap build` asks for both:
give the same one.)

**Back it up, today, in two places outside the repo:**
1. A USB drive kept at home: in Windows Explorer, open `\\wsl$\Ubuntu\home\<your user>\insidelabel-keys`
   and copy `insidelabel-upload.jks` to the drive.
2. A private Google Drive folder of your own (not the shared `InsideLabel` folder).

The **password** goes in your password manager, and on paper with the USB drive. Never in the same
Drive folder as the file, never in the repo, never in a chat or an email.

With Play App Signing (D-012) Google holds the key that signs what users install. Losing the upload
key is then recoverable: Play Console lets the account owner ask for an upload key reset. It still
costs days, so keep both copies.

**Its fingerprint** (for section 3):

```bash
$KEYTOOL -list -v -keystore ~/insidelabel-keys/insidelabel-upload.jks -alias upload | grep SHA256
```

### 2.3 Build and sign

```bash
cd ~/insidelabel && git checkout main && git pull
cd android
bubblewrap build --signingKeyPath ~/insidelabel-keys/insidelabel-upload.jks --signingKeyAlias upload
```

It asks for the two passwords, builds, and writes in `android/`:
- `app-release-bundle.aab`: **the file to upload to Play.**
- `app-release-signed.apk`: the same app as an APK, for installing by hand if ever needed.

Both are git-ignored. Check the bundle before uploading:

```bash
ls -l app-release-bundle.aab                     # about 1 to 2 MB expected (not measured here)
$(ls -d ~/.bubblewrap/jdk/jdk-17*)/bin/jarsigner -verify app-release-bundle.aab   # "jar verified."
```

If the build stops with "Could not find sdkmanager" or a licence error, run `bubblewrap doctor` again.
If it asks "Do you want to regenerate your project?", answer **No** and tell the build session:
`twa-manifest.json` and the project no longer match.

---

## 3. Asset links: the address bar goes only when both fingerprints are listed

The site serves https://insidelabel.ai/.well-known/assetlinks.json from `data/assetlinks.json`
(`api/main.py`, `tests/test_assetlinks.py`). It lists the package and the SHA-256 of each
certificate that may sign the app. A missing, empty or malformed file is a 404, so the merged branch
serves a 404 until the first fingerprint is added. That is expected: the app still opens, with an
address bar.

Two fingerprints, both kept:
- **The upload key** (section 2.2). It signs the APK you build yourself.
- **Google's app signing key.** It signs every install from Play, including internal and closed
  testing. It exists only after the first upload. **Without it, Play testers see an address bar.**

**Step A, after making the upload key.** Add its fingerprint as one row (copy the `SHA256:` value
exactly as keytool prints it: 32 upper-case pairs joined by colons):

```json
  "fingerprints": [
    {"sha256": "AB:CD:...:EF", "key": "upload", "added_on": "2026-10-02"}
  ]
```

Then either send the line to the build session, which adds it on its own small branch, or commit it
yourself. Run `pytest -q tests/test_assetlinks.py` before pushing: it fails on a fingerprint of the
wrong shape. After the merge, **on the server**:

```bash
sudo /opt/insidelabel/app/deploy/update.sh
curl -s https://insidelabel.ai/.well-known/assetlinks.json      # shows the package and the fingerprint
```

**Step B, after the first upload (section 4, step 2).** In Play Console: **Test and release > App
integrity** (on some accounts **Setup > App signing**), under "App signing key certificate", copy
the **SHA-256 certificate fingerprint**. Add it as a second row, `"key": "google_app_signing"`, the
same way, merge, then `update.sh` on the server and the same `curl`. The same page also shows the
upload key's fingerprint: it must match the one from step A.

**Check it the way Android does** (any browser):
https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://insidelabel.ai&relation=delegate_permission/common.handle_all_urls
It should list `ai.insidelabel.app.f` with both fingerprints. Android checks when the app is
installed, so after a change uninstall and reinstall the app from Play before looking again.

---

## 4. Play Console, in order (the app already exists)

The app was created on 2026-10-01 (Sushil): name InsideLabel, package `ai.insidelabel.app.f`,
en-GB, App, Free, Play App Signing terms accepted, automatic protection on. Menu names are as Play
Console shows them in 2026; if one has moved, search for it in the console.

1. **Upload key and bundle** (section 2), and **step A** of section 3.
2. **Internal testing first: Sushil's phone only, no review.** Test and release > Testing >
   Internal testing.
   - Testers tab: create an email list (for example "Sushil") with the Google account on your phone.
     Save. Copy the **opt-in link** shown there.
   - Create new release: upload `app-release-bundle.aab`; release name `1 (1)`; release notes
     "First test build."; Next; Save and publish (roll out to internal testing).
   - On the phone, open the opt-in link, accept, then install InsideLabel from the Play link the
     page gives.
3. **Step B** of section 3 (Google's fingerprint, now that a bundle is uploaded). Deploy it.
   Uninstall and reinstall the internal build.
4. **The phone checklist** (section 7) on the internal build. Nothing goes to a tester before it
   passes, except the limit screen, which comes later.
5. **App content** (Policy > App content): the answers in section 5. Every item there must be done
   before a closed release can be reviewed.
6. **Main store listing** (Grow users > Store presence > Main store listing): section 6. Icon:
   `android/store_icon.png` (512 x 512). Feature graphic and screenshots: section 6.
7. **Closed testing.** Test and release > Testing > Closed testing (the "Closed testing" track, or
   create one).
   - Countries and regions: India.
   - Testers: an email list with each tester's Google account (the address they use for Play on
     their Android phone). Recruit more than the minimum: people drop out.
   - Create a release: upload the same `app-release-bundle.aab` (or "Promote release" from internal
     testing, which reuses it). Save, then Publishing overview > **Send changes for review**. Unlike
     internal testing, this is reviewed by Google before testers can install it.
   - **App access for Google's review** (section 5.1): an invite code for the reviewers.
8. **Each tester needs two things:** the Play opt-in link for the closed track, and their own
   invite code for the server (D-102), on the server:
   `il tools/beta.py invite 1 --label T08` (OPERATIONS.md "Testers"). The code's join link opens
   the app if it is installed and the asset links check passed, otherwise Chrome; both share the
   same data (section 7).
9. **The closed-testing rule for new personal accounts.** Read it first-hand at
   https://support.google.com/googleplay/android-developer/answer/14151465 and on the Play Console
   **Dashboard**, which shows the count and days as they stand. This session could not open
   support.google.com (blocked here). A web search summary of that page (not read first-hand, to be
   checked) says: personal accounts created after 13 November 2023 must run a closed test with at
   least **12 testers opted in continuously for at least 14 days**, then **apply for production
   access** on the Dashboard; Google's review of that application "usually takes seven days or
   less". If those numbers hold, a closed test live on 6 October meets 14 days on 20 October, and
   leaves time for the production review before 5 or 6 November.

---

## 5. App content: draft answers, each traced

### 5.1 The short declarations

| Item | Answer | Basis |
|---|---|---|
| Privacy policy | https://insidelabel.ai/privacy.html | Sushil's choice. Served since this branch (it was a 404 before; `/privacy` serves the same page). See question 1 |
| App access | **All or some functionality is restricted.** Instructions: "InsideLabel is an invite-only beta. On 'Welcome to the InsideLabel beta', type the invite code below, tap 'Join the beta', then read 'Before you start' and agree. Then scan the barcode of any packaged food, or photograph its ingredient list." Give one code made for Google, on the server: `il tools/beta.py invite 1 --label PLAY --devices 10` | D-102: the server runs invite-only (`deploy/settings.env.example`); D-105 for "Before you start". Reviewers may use several devices, hence 10. Leave code PLAY out of the W4 count (D-055) |
| Ads | **No**, the app contains no ads | D-148 |
| Content rating | section 5.3 | |
| Target audience | **18 and over** only. "Could your store listing unintentionally appeal to children?" **No** | The app is for adults; parents add a child's profile and children aren't users (D-052, D-074, privacy page "InsideLabel is for adults"; DPDP map point 2: Gemini's terms bar apps "directed towards or ... likely to be accessed by individuals under the age of 18") |
| Data safety | section 5.2 | `docs/DPDP_DATA_MAP.md` |
| Government app | No | |
| Financial features | None | D-148: no payments |
| Health apps | see below | |
| News app | No | |
| Advertising ID | **No**, the app doesn't use it | No ads, no analytics SDK (DPDP map: "advertising ids" not collected); `android/app/build.gradle` has only `androidbrowserhelper` |

**Health apps declaration.** InsideLabel gives food label information (ingredients, allergens as
listed, additives and their FSSAI status, sugars) and is not a medical app: it diagnoses, treats or
monitors nothing and gives no medical advice. **Sushil confirms the exact option Play shows.** If the
list has a food or nutrition feature, that is the closest; choose nothing that says medical, disease,
clinical or medical device. If the only choice is between "health features" and none, say so to the
build session before answering. (The form's options couldn't be read here: support.google.com is
blocked in this session.)

### 5.2 Data safety, line by line from `docs/DPDP_DATA_MAP.md`

Data safety covers what the app collects, and for a TWA that is what the site collects, since the app
is the site. "Collected" means it leaves the phone. Data that stays on the phone is not collected.
Sending data to a service provider that processes it for us (Google Cloud, Gemini, Cloud Vision) is
not "sharing" (Google's own rule, https://developer.android.com/privacy-and-security/declare-data-use,
read 2026-10-01). Labels below are the form's own names; match them in the form.

**Overview questions**

| Question | Answer | Map row or source |
|---|---|---|
| Does the app collect or share any of the required user data types? | Yes | rows 1, 4, 5, 6, 8, 9, 11a |
| Is all of the user data collected by your app encrypted in transit? | Yes | not in the map: `deploy/Caddyfile` serves HTTPS only, with `Strict-Transport-Security` |
| Do you provide a way for users to request that their data is deleted? | Yes: "Delete my data" in the app (Your data), and by email to connect@insidelabel.ai | map point 6 (D-129, `POST /forget`); privacy page "Your choices" |
| Account creation | The app has no accounts: no name, phone number or email is asked for | map section 1 |

**Data types collected.** None is shared (only service providers, map section 3). None is processed
only ephemerally (all are stored). "Required" means the app can't work without it.

| Form type | What it is here | Map row | Purposes | Required or optional |
|---|---|---|---|---|
| Photos and videos > Photos | Pack photos (front, back, a screenshot of a listing) | 4, 10 | App functionality | Required for a pack not in the catalogue (a catalogue hit by barcode needs none) |
| Device or other IDs | The install id the browser makes | 1 | App functionality; Fraud prevention, security and compliance (rate limits, D-095); Analytics (days an install scanned, row 11a, D-055) | Required |
| Personal info > User IDs | The invite code a tester joined with | 2 | App functionality (invite-only beta) | Required while the beta is invite-only. See question 3 |
| Health and fitness > Health info | Each household member's avoid list (for example milk) sent with a scan | 6 | App functionality | Optional (profiles are optional). See question 4 |
| Personal info > Other info | Each household member's age band (baby to older) sent with a scan | 6 | App functionality | Optional. See question 4 |
| App activity > App interactions | Scan records linked to the install id for 30 days; days an install scanned; the app's recent trail in a problem report | 5, 11a, 9 | App functionality; Analytics | Required (scans); optional (problem reports) |
| App activity > Other user-generated content | Feedback text and rating; a problem report's comment | 8, 9 | App functionality (fixing problems); Developer communications | Optional |
| App info and performance > Crash logs | The errors a problem report carries | 9 | App functionality | Optional (sent only when the user sends a report, and shown first) |
| App info and performance > Diagnostics | User agent, language, screen size, network type in a problem report | 9 | App functionality | Optional |

**Not collected** (map section 2, "Not collected"): name, email address, phone number, address,
location (approximate or precise), contacts, messages, calendar, files, audio, web browsing,
financial info, installed apps, advertising ids. **Phone only, so not collected:** nicknames and the
parental consent tick (row 7), the shop list except the one list sent with a scan (row 7a, then part
of row 5). **Email** to connect@insidelabel.ai (row 13) is the user writing to us outside the app.

**Retention and deletion, as the map states them** (Play shows no retention periods, but the answers
must not contradict them): photos 30 days unless held (row 4, D-080, D-098); scans unlinked and
household details removed after 30 days (rows 5, 6, D-128); feedback and problem reports 12 months
(rows 8, 9); install id, invite link, agreement and day counts 12 months after last seen (rows 1 to 3,
11a); backups 14 days (row 12); "Delete my data" erases every row for the install id except a photo
that became a catalogue record (point 6).

**IP address** (row 11): held in memory only for the rate-limit windows (at most a day), never
stored, never used for location. The form has no IP address type. Recommended: not declared as
location. See question 5.

### 5.3 Content rating (IARC questionnaire)

Category: the one closest to a utility or reference app (Sushil picks it from the list shown; not a
game). Every content question is **No**:

| Question area | Answer | Why |
|---|---|---|
| Violence, fear, blood | No | food labels only |
| Sexuality, nudity | No | |
| Bad language | No | wording rules D-042, D-071 |
| Controlled substances (drugs, alcohol, tobacco) | No | the app shows what a scanned pack's label lists; it depicts or promotes none |
| Gambling, simulated gambling | No | |
| Users can interact or exchange content with each other | No | feedback and reports go to the operator only (map rows 8, 9) |
| Shares the user's location with other users | No | location is not collected |
| Digital purchases | No | D-148 |
| Unrestricted internet access (a web browser or search engine) | No | the app opens only insidelabel.ai/app/ |

Expected result: the lowest rating in each region. A low content rating doesn't change the target
audience, which stays 18 and over (5.1).

---

## 6. Store listing (en-GB)

Wording: D-042 and D-071 apply (no "safe", "healthy", "free from", "toxic" and the rest of
`tests/test_wording.py`'s list), the listing never names or judges a brand, and it describes only
what the app does today. `tests/test_wording.py` lints the block between the markers below, and
checks the lengths (name 30, short description 80, full description 4000 characters).

<!-- play-listing:start -->
**App name:** InsideLabel

**Short description:**
Read the label of Indian packaged food: allergens, additives and sugars listed.

**Full description:**

InsideLabel reads the label of Indian packaged food for you.

Scan a pack's barcode, or photograph its ingredient list. InsideLabel reads the list and tells you what is in it, in plain words.

• Allergens first. For each person in your household, it says whether a food they avoid, such as milk, peanuts or wheat, is listed on the label. When the photo isn't clear enough, it says it cannot confirm, rather than guess.
• Additives by name and INS number: what each one is for, and which are not permitted in India under FSSAI rules.
• Sugars: each kind of sugar the ingredient list names.
• Ingredients worth knowing, such as hydrogenated fat and maida, with what research has found and where it comes from.
• Your household: add each person's age band and the foods they avoid. Nicknames stay on your phone.
• Compare two to four packs side by side.
• Report a mistake from any result.

How it works
An AI model reads the photo. It decides nothing: fixed rules over tables we maintain make every finding, and they follow the regulations of FSSAI, the Food Safety and Standards Authority of India. Every additive in our tables records the FSSAI document it comes from.

What it doesn't do
InsideLabel quotes the label; it doesn't rate brands. It gives no medical advice and doesn't replace reading the pack yourself or advice from a doctor or dietitian.

Your data
No account, name, phone number or email. Pack photos are deleted 30 days after the scan, apart from the few cases the privacy page lists. "Delete my data" is in the app. Details: https://insidelabel.ai/privacy

InsideLabel is in a closed beta for adults in India.
<!-- play-listing:end -->

**Category:** Food & Drink (recommended over Health & Fitness: the app reads food labels).
**Contact:** isushilb@gmail.com. **Website:** https://insidelabel.ai.
Before production, remove or change the last line ("closed beta").

**Graphics** (Sushil makes them):
- App icon: `android/store_icon.png`, 512 x 512 (made from `web/icon-512.png`).
- Feature graphic: 1024 x 500, the name on the app's cream background (`#FBF9EE`), no pack, no brand.
- Phone screenshots, from the app on a phone, portrait. **No brand name, logo or pack art may be
  readable in any of them** (the listing never names a brand): use a pack whose name isn't shown,
  or crop. Suggested set, in this order:
  1. The scan screen, camera open on a barcode.
  2. A result's first screen: allergen line, headline, tiles (D-134).
  3. A tile's page: an additive with its FSSAI status and sources.
  4. The household: two profiles with age bands and avoid lists (nicknames that aren't real names).
  5. Compare with two or three packs (names cropped).
  6. "Your data", with "Delete my data".

---

## 7. Phone checklist (Sushil, on the build installed from Play)

Run it first on the internal build (section 4, step 4), again on the first closed build. Write the
date and the phone model next to each line.

- [ ] **No address bar** at the top when the app opens (asset links working). If there is one:
      section 3, both fingerprints, then uninstall and reinstall.
- [ ] Status bar and navigation bar cream in light mode, navy in dark mode; the splash shows the icon.
- [ ] **Camera and the barcode scanner** open and read a barcode (Chrome's BarcodeDetector inside the
      app). Chrome asks for the camera once, for insidelabel.ai.
- [ ] **The D-146 digit check** on a pack not in the catalogue: first 3 and last 4 digits large,
      "Yes, they match" goes on to the photo, "Scan again" goes back to the scanner. A catalogue pack
      shows its name with "Not this pack? Scan again".
- [ ] **A photo scan** of an ingredient list gives a result.
- [ ] **The D-148 limit screen** (15 photo scans a day), once `beta-limit` is deployed. It follows in
      the closed test's first week and doesn't hold the test up.
- [ ] **An invite code (D-102):** on a phone that hasn't joined, the join screen, a code, "Before you
      start"; a join link from a message opens the app (or Chrome) with the code filled in.
- [ ] **Data from the website is still there:** profiles and the shop list saved earlier in Chrome on
      insidelabel.ai show in the app (the app runs in Chrome and shares its site data).
- [ ] **"Report a mistake"** from a result sends, and the report shows on `/review`.
- [ ] The back button leaves a detail page, then the app; links to the privacy and about pages open.
- [ ] Rotating the phone keeps portrait.

---

## 8. Questions for Sushil

1. **The privacy page says "DRAFT for the invited beta ... still needs a legal review".** Play only
   needs a working URL, but the page is now the policy shown on the Play listing. Keep the draft line
   until the review, or change it?
2. **Health apps declaration:** confirm the exact option Play shows (5.1).
3. **The invite code as "User IDs"** (5.2): the map calls it the code a tester joined with, kept with
   the install id. Declaring it is the cautious answer; not declaring it would claim less than the map
   says. Recommended: declare.
4. **Avoid lists as "Health info", age bands as "Other info"** (5.2): the map doesn't say which form
   type they are. An allergy avoid list can be read as health information. Recommended: declare both
   (claiming less than we hold is the worse error).
5. **IP addresses** (5.2, row 11): kept in memory for a day at most for rate limits, never stored.
   Recommended: not declared. The DPDP reviewer may say otherwise.
6. **Closed-testing numbers** (section 4, step 9): check the page and the Dashboard; this file only
   has a search summary.
