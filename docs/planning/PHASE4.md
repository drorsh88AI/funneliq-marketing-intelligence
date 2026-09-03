# פאזה 4 — Auth

> **`planning_status: approved_for_execution`** (ר' §טו) **· `execution_status:
> awaiting_approval`** — checkpoints 1–10/16 הושלמו ואומתו; 11–16 ממתינים
> **להוראת ביצוע נפרדת** (זה אינו אישור להתחיל checkpoint 11)
> **Branch:** `feat/auth` (מקומי, טרם נדחף)
> **גבול הפאזה:** login עברי, session, sign-out, שני משתמשי דמו,
> `Depends(current_user)` בשרת. אין endpoints עסקיים, אין קריאת נתונים
> מהדפדפן, אין עיצוב מלא.
>
> ⚠ **המסמך נכתב בדיעבד** ועבר סבב ביקורת עצמאי (§יג) וסגירת שער תכנון
> בדיעבד (§טו). התכנון המקורי נכתב ואושר דרך מסמך תכנון של Claude Code (plan
> mode), לא דרך סבב ביקורת Codex פורמלי מראש — **הביצוע המקומי (1–9) התחיל
> לפני ששער התכנון נסגר; זה מתועד גלוי ב-§טו, לא מוסתר.** פרומפט ביקורת
> ל-Codex הוכן ונשלח למשתמש; **checkpoint 9 נסגר בפועל בסגירת בעל הפרויקט
> (ר' §טו סעיף 7), לא בהרצת הפרומפט מול Codex עצמו** — ההבחנה מתועדת שם.
>
> **`planning_status: approved_for_execution` עודכן בפועל — ר' §טו לתיעוד שני
> האישורים הנפרדים שהובילו אליו.** `execution_status` נשאר `awaiting_approval`:
> **checkpoint 11 ואילך דורש הוראת ביצוע נפרדת לכל אחד** — לא ניתן אישור גורף.

**מוסכמת תאריכים:** כל חותמת זמן במסמך היא **UTC**. השעון המקומי הוא UTC+3,
ולכן פעולה ב-`02.09 22:11 UTC` מופיעה בטרמינל כ-`03.09 01:11`.

---

## א. מטרת הפאזה

פאזה 3 הקימה RLS על `funnel_records`, אבל כל אכיפה שלה הוכחה **בסימולציית
role** (`set local role` + `request.jwt.claims` מוזרקים ידנית) — כי לא היה
משתמש אמיתי. ב-`funneliq` היו **0 משתמשים** (אומת ב-SQL לפני הביצוע).

פאזה 4 מייצרת את הצד החסר: משתמשים אמיתיים, התחברות מהדפדפן, session, ו-
dependency בשרת (`Depends(current_user)`) שאוכף `organization=northbound` —
התלות שפאזה 9 תבנה עליה.

**התוצאה המכוונת:** בוחן חיצוני פותח את `https://funneliq.onrender.com`,
נכנס עם פרטי דמו שנמסרו לו מראש, ורואה מסך "מחובר" עם התנתקות; זר בלי פרטים
לא יכול להירשם ולא יכול לקרוא כלום.

---

## ב. מצב מאומת — נבדק 02.09.2026, לא הונח

| ממצא | ראיה |
|---|---|
| `main` == `origin/main` == `c3b975b`, עץ נקי בתחילת הפאזה | `git rev-parse` |
| Render חי וער | `GET /health` → `200`, `{"status":"ok"}`, `0.131s` |
| Supabase `funneliq` תקין | `zbxqwcwiirnrfnkzpwri` · `ACTIVE_HEALTHY` · PG 17.6.1.166 · `eu-central-1` |
| **0 משתמשים** (לפני checkpoint 7) | `select count(*) from auth.users` → `0` |
| `app/` הכיל רק `main.py` (14 שורות, `/health`) | אין `auth.py`, אין `static/` |
| **אין צורך בתלות חדשה** | `requirements.txt` כבר נעל `supabase==2.31.0`, `PyJWT`, `python-dotenv`, `httpx`, `pytest` |
| בדיקות קיימות לפני הפאזה: **10** | `test_health.py` (1) + `test_load_data.py` (9) |
| טיפוסי שגיאה ב-`supabase_auth 2.31.0` | `AuthApiError` בעל `.status`; `AuthRetryableError` נוצר עם `status=0` לכשלי חיבור/timeout ועם `502/503/504/52x/530` ל-upstream (`helpers.py:134‑142`) — נקרא מהספרייה המותקנת |

---

## ג. הכרעות התכנון

**D1 — מסירת גישת הדמו: שני משתמשי דמו, מסירה ע"י המשתמש בעצמו.** *(הכרעת
שער `3→4`, נסגרה 02.09.2026.)*
`demo-northbound@funneliq.example.com` עם `organization=northbound` לזרימה
הרגילה · `demo-noorg@funneliq.example.com` בלעדיו, להדגמת דחיית 403. המשתמש
מוסר את שני הפרטים בעצמו; אינם במסך הלוגין, ב-README או בכל קובץ שנכנס ל-repo.

**D2 — הצד השרתי: `auth.py` + probe יחיד.** בלעדיו קריטריוני 401/403 אינם
ניתנים לבדיקה.

**D3 — אחרי התחברות: shell בלבד.** אין קריאת נתונים מהדפדפן (פאזה 11). אכיפת
ה-JWT האמיתי מוכחת **בשרת**, דרך `/api/me`.

**D4 — עיצוב: פונקציונלי RTL בלבד.** בלי Stitch ובלי design tokens (פאזות 7/10).

**D5 — יצירת משתמשים: `scripts/create_users.py`.** ה-Dashboard אינו מאפשר
להגדיר `app_metadata` ביצירה; `UPDATE` ידני על `auth.users.raw_app_meta_data`
הוא כתיבה ישירה לסכמת `auth` שאינה חוזרת ואינה מתועדת בקוד.

**D5א — טיפול בסיסמאות.** הסקריפט קולט סיסמאות ב-`getpass.getpass()` בלבד —
לא CLI args, לא משתני סביבה, לא קריאה מקובץ. המשתמש מריץ אותו בטרמינל שלו
(דפוס `supabase db push` מפאזה 3); אומת בפועל ש-`getpass` ב-Windows ניגש
ל-console ותולה תחת כלי לא-אינטראקטיבי, ולכן **הריצה בוצעה רק ע"י המשתמש**.

⚠ **סייג שנוסף בביקורת (B7):** לבקשת המשתמש נכתבו סיסמאות הדמו גם לתוך `.env`
המקומי **כשורות הערה `#`**, לעיון אישי. `python-dotenv` מתעלם משורות הערה,
ולכן הן אינן נטענות כמשתני סביבה ואינן נקראות ע"י הסקריפט. `.env` מוחרג
ואינו tracked. הקובץ אינו נקרא ע"י קלוד. ראיות והיקפן — §ה, E-secrets.

**D6 — בדיקת token פג: הורדה זמנית של JWT expiry.** ראיה אמיתית לפג-תוקף, לא
לטוקן פגום. פעולה ידנית, תיעוד ערך לפני/אחרי, שחזור מיידי. **טרם בוצע.**

**D7 — `current_user`: סדר 401/403.** `organization` נקרא מ-`app_metadata`
בלבד, לעולם לא מ-`user_metadata`.
```
אין Authorization / לא "Bearer <x>"      → 401  (בלי קריאת רשת)
הטוקן נדחה / user=None                    → 401
מזוהה, אך organization != northbound      → 403
אחרת → המשתמש
```

**D7א — מיפוי שגיאות מפורש לפי סוג (תיקון A1).** אין מיפוי גורף. הטבלה נגזרת
מטיפוסי הספרייה שנקראו בפועל (§ב), לא מהנחה:

| מקור | טיפוס | תגובת ה-API | נימוק |
|---|---|---|---|
| env חסר ב-`get_supabase()` | `KeyError` | **500** | תקלת קונפיגורציה בשרת — לא באשמת הקורא |
| GoTrue דחה את הטוקן | `AuthApiError` עם `status ∈ {400,401,403}` | **401** | הטוקן באמת לא תקף/פג |
| JWT פגום בצד הלקוח | `AuthInvalidJwtError` | **401** | credential לא תקין |
| GoTrue החזיר 5xx | `AuthApiError` עם `status ≥ 500` | **503** | ⚠ `500` **אינו** ברשימת ה-network codes ולכן מגיע כאן — מיפויו ל-401 היה מדווח תקלת upstream כבעיית credentials |
| כשל רשת / timeout / upstream 502‑530 | `AuthRetryableError` | **503** | תקלת תשתית |
| כל השאר | `AuthUnknownError` וכו' | **500** (מתפשט) | לא לבלוע שגיאות לא מוכרות |

`get_supabase()` נקרא **מחוץ** ל-`try`. אין `except Exception` רחב.

**D8 — הלקוח בשרת נבנה עם ה-publishable key בלבד.** ההכרעה עומדת בעינה. אימותה
מפוצל לשני חלקים מסומנים, כדי שלא תיטען כמוכחת לפני שהיא כזו:

- **D8-a — אימות מבצעי (checkpoint 14).** בדיקה מול `/api/config` החי המוכיחה
  שמה שמוגש הוא publishable, בדיוק שני שדות, בלי סמן secret, ומצביע על
  הפרויקט הנכון. פקודה מלאה — §ה, E-deploy. **אין הדפסת ערך מפתח.**
- **D8-b — אימות פונקציונלי (checkpoint 15).** ⚠ **זו לא החלטה פתוחה — ההכרעה
  (D8) סגורה.** מה שממתין הוא **בדיקת ביצוע עתידית ומתוזמנת**: ש-
  `auth.get_user(token)` אכן עובד עם publishable key בלבד מוכח כאשר `/api/me`
  עם טוקן `demo-northbound` מחזיר `200` (E-live, checkpoint 15). עד אז D8-b
  הוא סעיף ראיה שטרם נאסף, לא פרמטר תכנוני שטרם נקבע — האם לבנות את הלקוח עם
  publishable key בלבד כבר הוכרע ומומש (D8, `app/auth.py`); מה שנשאר הוא
  להוכיח שההכרעה עובדת בפועל מול API חי.

⚠ ניסוח קודם טען ש-D8 "אומת בפועל" על סמך כך ש-`SUPABASE_SECRET_KEY` אינו
נקרא ב-`app/`. זו ראיה לאי-שימוש, לא לתפקוד — הופרד כאן.

**D9 — `get_supabase()` עם `lru_cache(maxsize=1)`.** כדי ש-`pytest` יחליף אותו
כולו ב-`monkeypatch.setattr` בלי לגעת בקאש.

**D10 — `/api/config` נכשל רועש.** `500` אם משתני הסביבה חסרים — לא מחרוזת
ריקה. `/health` אינו תלוי בהם.

**D11 — CORS: אין. סטייה מנוסח `SPEC.md`.** הסטטי וה-API יוצאים מאותו origin
ב-Render, ו-`supabase-js` פונה ישירות ל-Supabase שמנהלת CORS משלה. אין קריאה
cross-origin שאנחנו שולטים בה; `CORSMiddleware` כאן הוא הגדרה למקרה שאינו
קיים. **לבחון מחדש אם יופיע origin שני** — דומיין מותאם, CDN לפני האפליקציה,
או frontend נפרד. (C1)

**D12 — `supabase-js` מ-CDN, גרסה מקובעת + SRI.**
`@supabase/supabase-js@2.58.0/dist/umd/supabase.min.js`, hash
`sha384-WmjsOVSSw3JNqIKfmDU35+uddOzBdP9PlYIWCg7xdnVOesjWVGpRcooOVheFFwH4`,
חושב מהקובץ שהורד (`openssl dgst -sha384`) ואומת יציב בשתי הורדות. אימות חוזר
של ההתאמה הוא בדיקה נפרדת — §ה, E-sri.

**D13 — סדר ה-mount.** `StaticFiles` על `/` נרשם **אחרי** כל ה-routes, אחרת
הוא בולע כל נתיב API.

**D14 — דומיין הדמו `@funneliq.example.com`.** שמור ב-RFC 2606. **אומת בפועל
שהוא מתקבל** — `create_user` הצליח (checkpoint 7).

**D15 — איסור הדפסת access token, סיסמה או מפתח לראיות.** חל גם על ראיות
דפדפן: ב-E-browser מתועדים **שמות מפתחות** ב-`localStorage` בלבד, לעולם לא
ערכיהם — ערך `sb-*` מכיל access token חי.

**D16 — `/api/config`: endpoint תשתיתי ציבורי, פאזה 4.** `SPEC.md` (שורות
1082, 1197) מאשר אותו כציבורי עם שני שדות בדיוק ואינו משייך אותו לפאזה;
ה-"phase 9" ב-`.env.example` הייתה הפניה מיושנת יחידה בהערה — **תוקנה**.
מחזיר `supabase_url` + `supabase_publishable_key` בלבד: בלי secret, בלי נתוני
משתמש, בלי מידע עסקי. הרחבה עתידית מחייבת שינוי ב-`SPEC.md`, לא החלטה מקומית.

---

## ד. תוצרי הקוד

```
app/main.py          ✅ routes + mount StaticFiles אחרון (D13)
app/auth.py          ✅ get_supabase, current_user, /api/config, /api/me
app/static/          ✅ index.html · style.css · app.js  (RTL, לוגין+shell+signout)
scripts/create_users.py  ✅ getpass, idempotent
tests/               ✅ test_config.py (3) · test_auth.py (8) · test_create_users.py (7)
```

### `/api/config` — צורת התשובה
```json
{"supabase_url": "https://<ref>.supabase.co", "supabase_publishable_key": "sb_publishable_..."}
```

### `/api/me` — צורת התשובה
```json
{"email": "...", "organization": "northbound", "role": "team_member"}
```

### `scripts/create_users.py` — הרצה בפועל, checkpoint 7

| מייל | `app_metadata` בפועל |
|---|---|
| `demo-northbound@funneliq.example.com` | `{organization: northbound, role: team_member, provider: email, providers: [email]}` |
| `demo-noorg@funneliq.example.com` | `{role: team_member, provider: email, providers: [email]}` — בלי `organization` |

⚠ **ממצא בזמן ריצה:** הסקריפט הורץ **פעמיים**. הראשונה יצרה את המשתמשים;
השנייה — באותה סיסמה, לפי אישור המשתמש — עדכנה `app_metadata` בלבד ולא נגעה
בסיסמה, לפי החוזה. אומת ב-SQL ש-`created_at` קדם ל-`updated_at` בכ-8 דקות
לשניהם. אין אי-ודאות לגבי הסיסמה החיה.

⚠ **סייג לאידמפוטנטיות (A5):** `find_user_by_email` סורק את `list_users()`
בלי pagination — כלומר את העמוד הראשון בלבד. בהיקף הנוכחי (2 משתמשים) זה
נכון, וכיוון הכשל בטוח: יצירה על מייל קיים תיכשל רועש ולא תשכפל. הטענה
"idempotent" תקפה **בהיקף הזה**.

---

## ה. בדיקות וראיות — שמונה קבוצות מופרדות

כל בדיקה משויכת ל-checkpoint אחד, עם תנאי, תוצאה צפויה וראיה. **אין ראיה
שמשויכת ל-"checkpoint 11" כללי.**

### E-local — pytest offline · checkpoint 7א · ✅ בוצע 03.09.2026 04:09 UTC

| תנאי | תוצאה צפויה | תוצאה בפועל |
|---|---|---|
| אין רשת, אין `.env`, אין credentials | כל הבדיקות עוברות | ✅ `33 passed` |
| env חסר + `Bearer <x>` על `/api/me` | **500** (לא 401) — D7א | ✅ `test_me_missing_env_is_500_not_401` |
| GoTrue דחה את הטוקן, `AuthApiError(status=401)` | **401** | ✅ `test_me_when_token_rejected_is_401` |
| JWT פגום, `AuthInvalidJwtError` | **401** | ✅ `test_me_when_jwt_malformed_is_401` |
| GoTrue upstream, `AuthApiError(status=500)` | **503** | ✅ `test_me_when_gotrue_5xx_is_503_not_401` |
| רשת/timeout, `AuthRetryableError(status=0)` | **503** | ✅ `test_me_when_network_retryable_is_503_not_401` |
| שגיאה לא-מוכרת (`RuntimeError`) | **מתפשטת, לא נבלעת כ-401** | ✅ `test_me_when_unexpected_error_propagates_not_swallowed` |
| מזוהה בלי `organization` (כולל הווריאנט ב-`user_metadata` בלבד) | **403** | ✅ קיים, עובר |

**33/33 עברו** (28 קודמים − 1 שהוחלף במקרים ספציפיים יותר + 6 חדשים לפי טבלת
D7א). `python -m pytest -q` → `33 passed`, בלי רשת ובלי `.env`. סוגי החריגה
(`AuthApiError`, `AuthRetryableError`, `AuthInvalidJwtError`) הם המחלקות
האמיתיות מ-`supabase_auth.errors`, לא stand-ins — הבדיקות מפעילות את הענפים
בפועל, לא רק את הצורה שלהם.

### E-sri — התאמת ה-SRI לקובץ ב-CDN · checkpoint 7א · ✅ בוצע 03.09.2026 04:09 UTC

| תנאי | תוצאה צפויה | תוצאה בפועל |
|---|---|---|
| הורדה חוזרת של ה-URL המקובע וחישוב `sha384` | זהה ל-hash שב-`index.html` | ✅ זהה: `sha384-WmjsOVSSw3JNqIKfmDU35+uddOzBdP9PlYIWCg7xdnVOesjWVGpRcooOVheFFwH4` |

בדיקה דטרמיניסטית, בלי credentials — קריאה ציבורית ל-CDN, לא ל-Supabase או
Render. אינה בודקת התנהגות דפדפן — זו E-cdn-fail.

### E-cdn-fail — התנהגות כשל CDN בדפדפן · checkpoint 15

| תנאי | תוצאה צפויה | ראיה |
|---|---|---|
| חסימת בקשת ה-CDN ב-DevTools, או SRI שאינו תואם | הודעת שגיאה **בעברית**; `#loading` מוסתר; הדף אינו נתקע | צילום מסך + שורת ה-console |

זהו התיקון A2: כיום `createClient` נקרא מחוץ ל-`try`, ולכן כשל CDN משאיר מסך
"טוען…" לנצח בלי שום הודעה.

### E-browser — מסע דפדפן מלא · checkpoint 15

| תנאי | תוצאה צפויה | ראיה |
|---|---|---|
| התחברות `demo-northbound` | מעבר ל-shell עם המייל | צילום מסך |
| רענון דף | ה-session שורד | צילום מסך |
| התחברות `demo-noorg` | ההתחברות **מצליחה**; הדחייה מתרחשת ב-`/api/me` (403), לא בלוגין | צילום מסך |
| sign-out | חזרה לטופס; אין מפתחות `sb-*` ב-`localStorage` | **רשימת שמות מפתחות בלבד** — לעולם לא ערכים (D15) |

### E-deploy — `/api/config` החי · checkpoint 14  *(D8-a + C3)*

תנאי: אחרי הזנת שני משתני הסביבה ב-Render ו-redeploy מוצלח.

```bash
RESP=$(curl -s -w '\n%{http_code}' https://funneliq.onrender.com/api/config)
CODE=$(printf '%s' "$RESP" | tail -n1)
BODY=$(printf '%s' "$RESP" | sed '$d')
echo "http_200:            $([ "$CODE" = 200 ] && echo true || echo false)"
printf '%s' "$BODY" | python -c '
import sys, json
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except Exception:
    print("json_valid:          false"); raise SystemExit(1)
key = d.get("supabase_publishable_key", "")
url = d.get("supabase_url", "")
print("json_valid:          true")
print("fields_exactly_two: ", sorted(d) == ["supabase_publishable_key", "supabase_url"])
print("key_is_publishable: ", isinstance(key, str) and key.startswith("sb_publishable_"))
print("no_secret_marker:   ", not any(m in raw for m in ("sb_secret", "service_role", "SECRET")))
print("url_matches_project:", url.startswith("https://zbxqwcwiirnrfnkzpwri.supabase.co"))
'
```

תוצאה צפויה: שש שורות `true`. **הפלט הוא בוליאנים בלבד — אין הדפסת ערך מפתח,
URL מלא או כל credential.** "בלי מידע עסקי" נאכף ע"י `fields_exactly_two`:
כל שדה נוסף מפיל אותה.

### E-live — טוקן אמיתי מול ה-API · checkpoint 15  *(D8-b)*

| תנאי | תוצאה צפויה | ראיה |
|---|---|---|
| `/api/me` עם טוקן `demo-northbound` | **200** + שלושת השדות | קוד סטטוס + גוף (המייל מותר; הטוקן לא) |
| `/api/me` עם טוקן `demo-noorg` | **403** | קוד סטטוס |
| `/api/me` בלי header | **401** | קוד סטטוס |
| התחברות שני המשתמשים | הצלחה; `organization` נוכח באחד וחסר בשני | **payload מפוענח בלבד**, בלי החתימה ובלי הטוקן הגולמי (D15) |

### E-expired — token פג תוקף · checkpoint 15  *(D6)*

| תנאי | תוצאה צפויה | ראיה |
|---|---|---|
| הורדת JWT expiry למינימום → התחברות → המתנה מעבר לתוקף → `/api/me` | **401** | קוד סטטוס |
| שחזור הערך המקורי | הערך חזר | ערך לפני/אחרי + אימות-אחרי מפורש |

### E-secrets — היגיינת סודות · checkpoint 8 ✅ (טענה 1) + checkpoint 15 ⏳ (טענה 2)  *(B7)*

שתי טענות **נפרדות**, ואין לערבב ביניהן — ולכן שני checkpoints שונים:

| טענה | מוכיחה | אינה מוכיחה |
|---|---|---|
| **1. `.env` מוחרג ואינו tracked** (checkpoint 8, מקומי בלבד). ✅ **בוצע 03.09.2026:** `git check-ignore -v .env` → `.gitignore:2`; `git ls-files --error-unmatch .env` → נכשל | שהקובץ לא ייכנס ל-commit | ❌ שום דבר על מה שהודפס לפלטים, ל-PR או ל-CI |
| **2. אף ערך רגיש לא הופיע בתוכן שנשמר** (checkpoint 15 — דורש PR/CI קיימים מ-checkpoint 11). סריקה נפרדת לפי ערך | שהערכים לא דלפו | — |

**מפרט סריקת הפלט (טענה 2), בלי הדפסת ערכים:** לקרוא את `.env` תוכניתית
ולחלץ ערכים **משורות `KEY=VALUE` וגם משורות ההערה `#` שמכילות את סיסמאות
הדמו** (D5א); לכל ערך להריץ חיפוש על עץ העבודה, על היסטוריית הגיט (`--all`),
על גוף ה-PR ועל לוגי ה-CI; **להדפיס רק את שם המשתנה ואת מספר ההתאמות**. תוצאה
צפויה: `0` לכל אחד. זהו הדפוס שהופעל בפאזה 3 (§ח.8), כולל תיקון ה-`read -r`
לקובץ בלי newline סופי.

### סיכום מצב הראיות

| קבוצה | checkpoint | מצב |
|---|---|---|
| F1 — הרשמה ציבורית חסומה | 6 | ✅ `HTTP 422 signup_disabled`; `auth.users` נשאר 2 |
| E-local | 7א | ✅ `33/33 עברו`, כולל 6 מקרי D7א חדשים |
| E-sri | 7א | ✅ hash זהה מול ה-CDN החי |
| E-deploy | 8 | ⏳ |
| E-live | 9 | ⏳ |
| E-expired | 10 | ⏳ |
| E-cdn-fail · E-browser · E-secrets | 11 | ⏳ |

---

## ו. סדר ביצוע

כל checkpoint ממופה לקריטריון קבלה מ-§ז (או מסומן "תשתית" אם אינו מייצר
קריטריון בעצמו — רק מאפשר את מה שאחריו), לתנאי הביצוע שלו, ולראיה.

| # | פעולה | קריטריון קבלה (§ז) | תנאי | ראיה | סטטוס |
|---|---|---|---|---|---|
| 1 | סנכרון `main`, פתיחת `feat/auth` | תשתית | — | `git rev-parse` | ✅ 02.09 21:35 UTC |
| 2 | `auth.py` + `/api/config` + `/api/me` + mount | `401`/`403` נכונים; `/api/config` ציבורי | checkpoint 1 | E-local | ✅ 02.09 21:36 |
| 3 | `test_config.py` + `test_auth.py` | אותם קריטריונים — יוצר את הראיה | checkpoint 2 | `pytest -q` | ✅ 02.09 21:39 |
| 4 | `app/static/*` | מסך התחברות RTL; session; sign-out | checkpoint 2 | נבדק מקומית מול `uvicorn` | ✅ 02.09 21:37 |
| 5 | `create_users.py` + בדיקות mock | תשתית ל-6/7 | — | 7 בדיקות mock | ✅ 02.09 21:39 |
| 6 | כיבוי הרשמה ציבורית + F1 | הרשמה ציבורית כבויה | — | F1 (`422 signup_disabled`) | ✅ 02.09 22:11 |
| 7 | הרצת `create_users.py` + אימות SQL | שני משתמשי דמו, `app_metadata` נכון | checkpoint 5, 6 | SQL קריאה-בלבד | ✅ 02.09 21:57 |
| 7א | תיקוני הביקורת: D7א (A1) · כשל CDN (A2) · E-local חדשות · E-sri · מעבר תיעוד | שגיאת קונפיג/תשתית ≠ `401`; SRI תואם; מסמכים עקביים | checkpoints 2–7 | `pytest -q` 33/33; hash SRI | ✅ 03.09 04:09 UTC |
| 8 | `E-secrets` טענה 1 + סקירת עקביות סופית | `.env` מוחרג ואינו tracked | — | `git check-ignore`/`git ls-files` | ✅ 03.09 14:14 |
| 9 | סגירת ביקורת נוספת על התכנון | תשתית (תהליכי — סוגר את שער התכנון, לא קריטריון מוצר) | — | **סגירת בעל הפרויקט**, לא ריצת כלי Codex — ר' §טו סעיף 7 | ✅ **done, 03.09.2026 14:58 UTC** |
| 10 | יישום תיקונים אם יידרשו מ-9 + `pytest -q` מלא מחדש | תלוי בממצאי 9 — **9 סגר blocker:none / important:none / cosmetic:none, אין תיקון ליישם** | checkpoint 9 | `pytest -q` → `33 passed` | ✅ **done, 03.09.2026 15:07 UTC** |
| 11 | (1) `git commit` → (2) `git push` על `feat/auth` → (3) פתיחת PR → (4) CI ירוק | CI ירוק בלי credentials | checkpoint 10 | ריצת CI | ⏳ not_started |
| 12 | אישור ומיזוג ל-`main` | תשתית (מאפשר 13–16; אישור נפרד, בלתי הפיך) | checkpoint 11, CI ירוק | merge commit | ⏳ not_started |
| 13 | Render: `SUPABASE_URL`+`SUPABASE_PUBLISHABLE_KEY` (בלי secret) + redeploy | תשתית ל-14 | checkpoint 12 | Render Dashboard (ידני — אין כלי MCP) | ⏳ not_started |
| 14 | אימות `/health`+`/api/config` חי — **E-deploy** | `/api/config` ציבורי חי; Render מדבר עם הפרויקט הנכון (C3) | checkpoint 13 | E-deploy (D8-a) | ⏳ not_started |
| 15 | **E-live**(D8-b)·**E-expired**(D6)·**E-browser**·**E-cdn-fail**·`E-secrets` טענה 2 | `401`/`403` חי; token פג; session/sign-out; RTL; כשל CDN בעברית; אין סוד בגיט/PR/CI | checkpoint 14 | חמש קבוצות ראיה נפרדות | ⏳ not_started |
| 16 | מסירת פרטי שני משתמשי הדמו למרצה + סגירה | פרטי הדמו נמסרו למרצה | checkpoint 15 | אישור המשתמש | ⏳ not_started |

**תלויות:** 12 לפני 13 — קוד פאזה 4 חייב להיות ב-`main` לפני שהוא רלוונטי
ל-Render, ש-`render.yaml` מגדיר לפרוס מ-`branch: main`. **אומת אמפירית
03.09.2026:** לפני שקוד פאזה 4 היה ב-`main`, `/api/config` על השירות החי
החזיר `404` (ה-route לא קיים בקוד הפרוס) — לא `500` (env חסר). הגדרת env vars
לפני מיזוג הייתה תקינה אך לא ניתנת לאימות. 13 לפני 14, 14 לפני 15.
**כל checkpoint מ-11 ואילך דורש אישור נפרד** (8–10 בוצעו — ר' §יד לתיעוד
שהביצוע המקומי החל לפני סגירת שער התכנון).

**מוסכמת commit — repo ציבורי.** ⚠ עד עכשיו לא תועד בשום מקום בפאזה זו: זהו
repo ציבורי (`funneliq-marketing-intelligence`, נוצר בפאזה 1). הודעות commit
ו-PR נושאות `Co-Authored-By`, **ולא** שורת `Claude-Session` (קישור לסשן) —
זו האחרונה נשארת פרטית. מוסכמה זו חלה על checkpoint 11 ואילך; לא הייתה
רלוונטית לפני כן כי לא בוצע עדיין שום commit בפאזה 4.

---

## ז. קריטריוני קבלה

| קריטריון | ראיה | מצב |
|---|---|---|
| מסך התחברות עברי RTL, נגיש במקלדת | E-browser | ⏳ |
| הרשמה ציבורית כבויה | F1 | ✅ |
| שני משתמשי דמו מאומתים מראש, `app_metadata` נכון | SQL, checkpoint 7 | ✅ |
| `401` בלי token / עם token שנדחה | E-local + E-live | ⏳ (E-local ✅ — 33/33) |
| `403` עם token בלי הרשאה | E-local + E-live | ⏳ (E-local ✅ — 33/33) |
| **שגיאת קונפיגורציה או תשתית אינה מוחזרת כ-`401`** (D7א) | E-local | ✅ **חדש, נסגר** — 6 מקרים |
| `401` על token פג תוקף | E-expired | ⏳ |
| session שורד רענון · sign-out מנקה | E-browser | ⏳ |
| **כשל טעינת `supabase-js` מוצג כשגיאה בעברית, לא כ-loading אינסופי** | E-cdn-fail | ⏳ **חדש** — קוד תוקן ב-7א, ראיית דפדפן ב-15 |
| **ה-SRI המקובע תואם לקובץ שב-CDN** | E-sri | ✅ **חדש, נסגר** |
| `/api/config` ציבורי, שני שדות, בלי secret ובלי מידע עסקי | E-local + E-deploy | ⏳ (E-local ✅) |
| **ה-Render הפרוס מדבר עם פרויקט Supabase הנכון** (C3) | E-deploy | ⏳ **חדש** |
| CI ירוק בלי credentials | checkpoint 11 | ⏳ |
| `.env` מוחרג ואינו tracked | E-secrets, טענה 1 | ✅ |
| **אף ערך רגיש לא הופיע בגיט, ב-PR או ב-CI** | E-secrets, טענה 2 | ⏳ **הופרד מהשורה שמעליה** |
| **מסמכי הפאזה עקביים פנימית ומול המצב בפועל** | מעבר התיעוד ב-7א | ✅ **חדש, נסגר** |
| פרטי שני משתמשי הדמו נמסרו למרצה | אישור המשתמש | ⏳ |

---

## ח. סיכונים ובלמים

| סיכון | מענה | מצב |
|---|---|---|
| כשל בהזנת משתני Render מתחזה ל-401 | D7א + E-deploy | ⏳ D7א ✅ (קוד+33 בדיקות); E-deploy ממתין ל-checkpoint 14 (אחרי מיזוג ל-`main`, checkpoint 12) |
| `StaticFiles` בולע את ה-API | mount אחרון; כיסוי רגרסיה משתמע — בדיקת ה-401 תיפול ל-404 אם הסדר יתהפך | ✅ |
| CDN לא זמין במבחן הקבלה | גרסה מקובעת + SRI (E-sri) · הודעת שגיאה בעברית (E-cdn-fail) · מסלול מילוט: vendoring ל-`static/vendor/` | E-sri ✅ · קוד ה-catch תוקן ב-7א · ראיית דפדפן (E-cdn-fail) ⏳ ב-11 |
| `get_user()` = round-trip רשת לכל בקשה מוגנת | מקובל בהיקף הנוכחי; *ponytail:* JWKS מקומי אם המדידה בפאזה 9/12 תכאב | פתוח |
| Supabase דוחה דומיין `example.com` | נבדק — מתקבל בפועל | ✅ נסגר |
| JWT expiry לא הוחזר אחרי E-expired | אימות-אחרי מפורש בתוך checkpoint 15 | ⏳ |
| טוקן/סיסמה נשפכים לראיה | D15 + E-secrets טענה 2 + כלל "שמות מפתחות בלבד" ב-E-browser | ⏳ |
| הרצה כפולה של `create_users.py` | קרה בפועל; נסגר — אותה סיסמה בשתי הריצות | ✅ נסגר |

---

## ט. מה פאזה 4 **אינה** כוללת

`features.py` · `predict.py` · `insights.py` · endpoints עסקיים · קריאת נתונים
מהדפדפן · design tokens ו-Stitch · **rate limiting מכל סוג** · "זכור אותי" ·
שחזור סיסמה עצמי · טבלת `users` משלנו · rotation מותאם של refresh token.

---

## י. פערי תיעוד

| קובץ | פער | מצב |
|---|---|---|
| `.env.example` | נקב `(phase 9)` | ✅ תוקן |
| `codex-review.md` | חסרו D1, D5א, D11, D16 ביומן ההכרעות | ✅ נוספו |
| `render.yaml` | אין `envVars` | ✅ תוקן — `sync: false` לשני השדות, בלי ערכים, `SUPABASE_SECRET_KEY` נעדר במפורש. שינוי מקומי בלבד, טרם נדחף |
| `SPEC.md` §Auth | טרם מתעד שהכרעת השער נסגרה | ⏳ פתוח |
| `ROADMAP.html` | פריט checkpoint 7א | ✅ נוסף, מסומן `done` עם ראיה |

---

## יא. מעמד המסמך

המשתמש אישר ביצוע פאזה 4 בהיקף מוגבל, checkpoint אחר checkpoint, ולא אישור
גורף. checkpoint 7א בוצע 03.09.2026 04:09 UTC (§ה, §ו). **checkpoint 8 ואילך
ממתין לאישור נפרד** — לא ניתן אישור גורף לשאר הפאזה.

---

## יב. מה נדרש לפני סגירה

1. checkpoints 11–16 (§ו) — 9, 10 בוצעו.
2. סגירת פער §י שנותר (`SPEC.md` §Auth — `render.yaml` כבר נסגר).
3. ✅ **בוצע 03.09.2026 14:31 UTC:** `planning_status` עודכן ב-`ROADMAP.html`
   דרך `under_review` ל-`approved_for_execution`, בשני אישורים נפרדים של
   המשתמש — ר' §טו.

---

## יג. תוצאת סבב הביקורת — 02–03.09.2026

הביקורת בוצעה על גרסת המסמך שנכתבה בדיעבד, מול הקוד בפועל ולא מול המסמך בלבד.
**ממצא A1 אומת בהרצה** (`config → 500` מול `me → 401` באותו מצב env חסר), ולא
נטען מתוך קריאת קוד.

| ממצא | הכרעה | מקור ההכרעה | לאן נכנס |
|---|---|---|---|
| **A1** — `except Exception` ממסך שגיאת קונפיגורציה כ-401 | **התקבל**, והורחב: מיפוי מפורש לפי סוג שגיאה; אין מיפוי אוטומטי של `AuthRetryableError` ל-401 | הכרעת המשתמש | D7א · E-local · קריטריון חדש · checkpoint 7א |
| **A2** — כשל CDN משאיר מסך טעינה תקוע | **התקבל** | הכרעת המשתמש | E-cdn-fail · קריטריון חדש · checkpoint 7א/11 |
| **A3** — חסימת כפתור בזמן sign-in | **נדחה ויורד מהתוכנית** | הכרעת המשתמש | — |
| **A4** — `onAuthStateChange` + `getSession()` כפולים | **יורד** — אין קריטריון קבלה | הכרעת המשתמש, סבב קודם | — |
| **A5** — `list_users()` בלי pagination | **התקבל כסייג תיעודי**, לא כשינוי קוד | הכרעת המשתמש | §ד |
| **B1** — D8 הצהיר "אומת בפועל" ללא בסיס | **התקבל**; D8 **לא הוסר** אלא פוצל ל-D8-a מבצעי ו-D8-b פונקציונלי | הכרעת המשתמש | D8 · E-deploy · E-live |
| **B2–B6** — חמש סתירות פנימיות | **התקבלו** | הכרעת המשתמש | §ב · §ה · §ז · D16 · מוסכמת התאריכים |
| **B7** — הסיסמאות ב-`.env` לא תועדו | **התקבל**, והורחב: הפרדה מפורשת בין מה ש-`git check-ignore`/`git ls-files` מוכיחים לבין סריקת פלט | הכרעת המשתמש | D5א · E-secrets · §ז (שתי שורות נפרדות) |
| **C1** — "לבחון מחדש אם יופיע origin שני" | **התקבל** | הכרעת המשתמש | D11 |
| **C3** — אימות שה-Render מצביע על הפרויקט הנכון | **התקבל**; פקודת הבדיקה הושלמה (HTTP, JSON, שדות, סוג מפתח, סמן secret, URL) | הכרעת המשתמש | E-deploy · קריטריון חדש |
| **C4** — תיעוד תוצאת הביקורת | **התקבל**; "תוצאת סבב" לבדה אינה ראיה — נדרש פירוט קבלה/דחייה ומקור | הכרעת המשתמש | §יג זה |

**נשמרו ללא שינוי** לפי הנחיה מפורשת: D1 (שני משתמשי הדמו) · הרשאה לפי
`app_metadata` · D5/D5א ומנגנון ה-`getpass` · D13 · D16 (`/api/config`
כ-endpoint תשתיתי בלבד) · D11 (מלבד תוספת C1) · D7 · היעדר endpoints עסקיים ·
היעדר עיצוב מלא.

**תיקון לרשומה:** בסבב הקודם נימקתי את A3 בכך ש-`supabase/config.toml` מגביל
sign-ins ל-30 ל-5 דקות לכל IP. הנימוק שגוי — `config.toml` הוא קונפיגורציית
הסביבה המקומית של ה-CLI, ובפרויקט הזה מעולם לא הופעל stack מקומי ("אין
Docker", פאזה 3), ולכן אינו מעיד על התנהגות הפרויקט המתארח. הטענה הוסרה, ואיתה
A3. **rate limiting מכל סוג נמצא מחוץ לפאזה 4** (§ט).

---

## יד. סדר הביצוע נבנה מחדש — 03.09.2026

**ממצא אמפירי, לא תיאורטי.** בניסיון לבצע את מה שהיה checkpoint 8 (env vars
ב-Render), נבדק המצב החי לפני כל שינוי: `GET /health` → `200` (אחרי cold
start); `GET /api/config` → **`404`**, לא `500`. ה-`404` מוכיח של-Render אין
בכלל את ה-route — כי `render.yaml` פורס מ-`branch: main`, ו-`main` עדיין
ב-`c3b975b` (סוף פאזה 3). כל קוד פאזה 4 (`app/auth.py` וכו') יושב רק על
`feat/auth` מקומית, ומעולם לא נדחף. הסדר הקודם (env vars/redeploy ב-8, ורק
commit/push/PR ב-11) הפוך: הוא ניסה לאמת endpoint שהקוד הפרוס לא יכול להכיל.

**ההכרעה:** commit → push → PR → CI → מיזוג ל-`main` **מקדימים** כל פעולת
Render/JWT/live-verification. checkpoints 8–16 (§ו) הוחלפו בהתאם. checkpoint
11 מפרט במפורש ארבעה שלבים בזה אחר זה — `commit` לא נשאר משתמע.

**מה לא השתנה:** checkpoints 1–7א (בוצעו לפני שהממצא עלה) נשארים כפי שהיו,
ללא renumbering. השינוי חל רק על מה שנותר. לא בוצעה שום פעולה על Render,
Supabase, JWT, git commit/push/PR בעקבות העדכון הזה — עדכון תכנון בלבד.

| מה | הכרעה | מקור |
|---|---|---|
| סדר Render לפני commit/push/PR | **שגוי**, הפוך | ממצא אמפירי (`404`), 03.09.2026 |
| סדר מחדש: local → ביקורת → commit/push/PR/CI → מיזוג → Render → live evidence | **התקבל** | הכרעת המשתמש |
| checkpoint 11: commit מפורש לפני push, ואז PR, CI, מיזוג נפרד (12) | **התקבל** | הכרעת המשתמש |

---

## טו. סגירת שער תכנון — 03.09.2026

**זהו תיעוד סגירת שלב התכנון, לא אישור ביצוע.** לפי בקשת המשתמש:

1. **`PHASE4.md` הוא הגרסה הסופית לביקורת.** אין בו החלטה מהותית פתוחה.
   הבדיקה היחידה שנמצאה בניסוח כ"הנחה פתוחה" — D8-b — תוקנה: ההכרעה (D8, לבנות
   את הלקוח עם publishable key בלבד) סגורה ומומשת; מה שנשאר הוא בדיקת ביצוע
   מתוזמנת (checkpoint 15), לא פרמטר תכנוני שטרם נקבע. שאר סימוני ה-`⏳`
   במסמך הם ביצוע ממתין, לא תכנון פתוח.
2. **כל checkpoint ממופה** לקריטריון קבלה (או "תשתית" אם אינו מייצר קריטריון
   בעצמו), לתנאי ביצוע ולראיה — טבלת §ו המורחבת.
3. `ROADMAP.html`: `planning_status` פאזה 4 → `under_review`.
4. **⚠ תיעוד גלוי, לא מוסתר: הביצוע המקומי (checkpoints 1–8) התחיל ואושר
   checkpoint-אחר-checkpoint לפני ששער התכנון נסגר פורמלית.** זה לא נמחק
   ולא משוחזר — כל הזמנים, הראיות וההחלטות ב-§ו נשארים בדיוק כפי שתועדו
   בזמן אמת. מה שקורה כאן הוא סגירה פורמלית **בדיעבד** של השער עצמו, לפי
   מדיניות השער האחיד ב-`SPEC.md`, לא מחיקת מה שכבר קרה. הפער תועד לראשונה
   ב-`ROADMAP.html` כשעלה (לפני checkpoint 1, 03.09.2026) ונשמר גלוי בכל
   עדכון מאז — ראו הערת ה-⚠ בראש מסמך זה ו-§יג.
5. **תוקנה הסתירה:** `execution_status` פאזה 4 שונה מ-`in_progress` ל-
   `awaiting_approval` (ערך תקני מ-4 האפשרויות ב-`ROADMAP.html`) — **לא**
   `done` (רק 8/16 checkpoints בוצעו), **ולא** נותר `in_progress` לצד
   `planning_status` שאינו `approved_for_execution`. זו הפעם הראשונה ששני
   השדות עקביים מאז שהפער עלה.
6. **`codex-review.md` לא שונה בסבב הזה.** יומן ההכרעות שם מרכז החלטות
   ברמת `SPEC.md`/חוצות-פאזות (D1, D5א, D11, D16 כבר נרשמו שם). סגירת שער
   תכנון פנימית לפאזה 4 ומעבר סטטוסי `ROADMAP.html` הם ניהול מצב שמתועד
   כאן וב-`ROADMAP.html` עצמו — אין בו קביעה חדשה שסותרת או מוסיפה ל-`SPEC.md`.
7. **checkpoint 9 נסגר 03.09.2026 14:58 UTC — ⚠ הבחנה מפורשת בין מה שתוכנן
   למה שקרה בפועל:** checkpoint 9 הוגדר במקור כ"תוצאת סבב ביקורת Codex" —
   הרצה בפועל של הפרומפט שהוכן מול כלי Codex חיצוני. **זה לא מה שקרה.** מה
   שקרה בפועל הוא **ביקורת עצמאית של בעל הפרויקט** על `PHASE4.md` מול
   `ROADMAP.html` (מספור תת-המשימות, תלויות, סטטוסים ותוצר הביקורת), עם
   תוצאה `blocker: none, important: none, cosmetic: none`. בעל הפרויקט
   הכריע במפורש (לאחר שהובהר לו ההבדל) **שסגירתו-שלו מחליפה את הרצת
   Codex** — לא שהיא שקולה לה מבלי לומר זאת. הפרומפט שהוכן ל-Codex נשאר
   פתוח לשימוש עתידי אם יידרש, אבל אינו נדרש עוד לסגירת checkpoint 9.

**עדכון 03.09.2026 14:31 UTC:** המשתמש אישר את סגירת שער התכנון, ולאחר מכן
נתן אישור נפרד ומפורש נוסף — `"planning_status: approved_for_execution"` —
ו-`planning_status` עודכן בהתאם ב-`ROADMAP.html` ובכותרת מסמך זה.
`execution_status` נשאר `awaiting_approval` במכוון: אישור זה סוגר את שער
התכנון בלבד, ואינו הוראת ביצוע ל-checkpoint 11 ואילך — זו נדרשת בנפרד.
