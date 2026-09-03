# פאזה 4 — Auth

> **`planning_status: approved_for_execution`** (ר' §טו) **· `execution_status:
> awaiting_approval`** — checkpoints 1–15/16 הושלמו ואומתו (E-expired בתוך 15
> נזנח בהכרעה מתועדת); 16 ממתין
> **להוראת ביצוע נפרדת** (זה אינו אישור להתחיל checkpoint 13 — שינוי ב-Render)
> **Branch:** `feat/auth` — נדחף, `PR #14` **מוזג ל-`main`** (merge commit
> `91e822f`, 03.09.2026 15:45 UTC), CI ירוק על `main`
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
> **checkpoint 16 (האחרון) דורש הוראת ביצוע נפרדת** — לא ניתן אישור גורף.

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

**D6 — בדיקת token פג: הורדה זמנית של JWT expiry.** ⚠ **נזנח, 03.09.2026
(הכרעת המשתמש) — מגבלת פלטפורמה, לא ביטול המנגנון עצמו.** נבדקו שלושה מקומות
ב-Supabase Dashboard (Free plan) — Sessions (Pro-gated), Sign In/Providers,
Email provider panel (רק Email OTP expiration) — ואין דרך לשנות את משך תוקף
ה-access token. פרטים מלאים ב-§ה, E-expired. ההתנהגות הנבדקת (`401` על טוקן
שנדחה) מכוסה ב-E-local ע"י mock.

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

- **D8-a — אימות מבצעי (checkpoint 14). ✅ נסגר, 03.09.2026 16:11 UTC.** בדיקה
  מול `/api/config` החי המוכיחה שמה שמוגש הוא publishable, בדיוק שני שדות,
  בלי סמן secret, ומצביע על הפרויקט הנכון. פקודה מלאה — §ה, E-deploy —
  6/6 `true`. **אין הדפסת ערך מפתח.**
- **D8-b — אימות פונקציונלי (checkpoint 15). ✅ נסגר, 03.09.2026 18:43 UTC.**
  `auth.get_user(token)` אכן עובד עם publishable key בלבד — מוכח: `/api/me`
  עם טוקן `demo-northbound` מחזיר `200` (E-live). הבנייה עם publishable key
  בלבד הוכרעה ומומשה (D8, `app/auth.py`) *וגם* אומתה בפועל מול API חי.

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

### E-cdn-fail — התנהגות כשל CDN בדפדפן · checkpoint 15 · ✅ בוצע 03.09.2026

| תנאי | תוצאה צפויה | בפועל |
|---|---|---|
| `window.supabase` שבור (מדמה כשל CDN/SRI), `app.js` האמיתי מהשרת מורץ נגד `/api/config` האמיתי | הודעת שגיאה **בעברית**; `#loading` מוסתר; הדף אינו נתקע | ✅ `loading_hidden=true`, `config_error_hidden=false`, טקסט: "שגיאה בטעינת ההגדרות. נסו לרענן את הדף.", `login_section_hidden=true`. צילום מסך |

בוצע בדפדפן אמיתי מול `https://funneliq.onrender.com` (לא מוק): `window.supabase`
נשבר ידנית, `/app.js` האמיתי נשלף מהשרת והורץ מחדש בהקשר הדף החי, נגד
`/api/config` האמיתי. זו בדיוק התיקון A2: `createClient` תחת אותו `try/catch`
כמו ה-`fetch` — כשל מציג הודעה, לא נתקע.

### E-browser — מסע דפדפן מלא · checkpoint 15 · ✅ בוצע 03.09.2026 19:12 UTC

| תנאי | תוצאה צפויה | בפועל |
|---|---|---|
| התחברות `demo-northbound` | מעבר ל-shell עם המייל | ✅ "מחובר כ־demo-northbound@funneliq.example.com" עם כפתור התנתקות. צילום מסך |
| רענון דף | ה-session שורד | ✅ אחרי F5 — עדיין מחובר, לא חזר לטופס |
| התחברות `demo-noorg` | ההתחברות **מצליחה**; הדחייה מתרחשת ב-`/api/me` (403), לא בלוגין | **מכוסה ב-E-live** (`sign_in_with_password` אמיתי + `/api/me`→403) — לא נבדק שוב דרך ה-UI כי זה אותה קריאה בדיוק שהדפדפן היה מבצע, לא נדרש שכפול |
| sign-out | חזרה לטופס; אין מפתחות `sb-*` ב-`localStorage` | ✅ שם המפתח `sb-zbxqwcwiirnrfnkzpwri...` נעלם אחרי לחיצה על "התנתקות" |

⚠ **ממצא D15 אמיתי, לא רק סיכון תיאורטי:** בזמן הבדיקה נשלח צילום מסך שבו
`access_token`/`refresh_token` היו **מורחבים בערכים אמיתיים**, לא רק שם
המפתח. תועד, לא הועתק לשום מקום, ולא נעשה בו שימוש. מהשלב הזה נדרשו **רק שמות
מפתחות** בהמשך.

**בדיקת המשך (03.09.2026 19:24 UTC), אחרי ההתנתקות:** שאילתת SQL קריאה-בלבד
מול `auth.sessions`/`auth.refresh_tokens` הראתה **0 sessions ו-0 refresh
tokens פעילים** ל-`demo-northbound`. זה עקבי עם דחיית הטוקן החשוף (GoTrue
קושר access token ל-`session_id` ובודק את קיומו ב-`/auth/v1/user` — אותה
קריאה ש-`current_user` מבצע) — **אך זו הסקה ממצב ה-session ב-DB, לא בדיקה
ישירה של הטוקן הספציפי מהצילום עצמו**, שאינו ברשותנו (מעולם לא נשמר, D15).
לא בוצעה בדיקת 401 אמפירית מול טוקן שפג/בוטל בפועל.

באותה בדיקה נמצא ש-`demo-noorg` (משתמש דמו שני, **לא** זה שנחשף בצילום) מחזיק
refresh token פעיל שמעולם לא בוצע לו sign-out. ניסיון למחוק אותו ישירות דרך
SQL על `auth.sessions` **נחסם ע"י ה-sandbox permission classifier** (כתיבה
ישירה לסכמת auth) — לא בוצע עקיפה. הניקוי הזה **אופציונלי ונפרד**, מתבצע
ע"י המשתמש בלבד דרך Supabase Dashboard, ואינו חוסם את סגירת checkpoint 15
או את המשך התהליך.

### E-deploy — `/api/config` החי · checkpoint 14 · ✅ בוצע 03.09.2026 16:11 UTC  *(D8-a + C3)*

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

### E-live — טוקן אמיתי מול ה-API · checkpoint 15 · ✅ בוצע 03.09.2026 18:43 UTC  *(D8-b)*

| תנאי | תוצאה צפויה | בפועל |
|---|---|---|
| `/api/me` עם טוקן `demo-northbound` | **200** + שלושת השדות | ✅ `200`, `organization=northbound` |
| `/api/me` עם טוקן `demo-noorg` | **403** | ✅ `403` (ההתחברות עצמה הצליחה) |
| `/api/me` בלי header | **401** | ✅ `401` |
| התחברות שני המשתמשים | הצלחה; `organization` נוכח באחד וחסר בשני | ✅ נוכח ב-`demo-northbound`, `<absent>` ב-`demo-noorg` — **payload מפוענח בלבד**, בלי החתימה ובלי הטוקן הגולמי (D15) |

**D8-b נסגר** — `auth.get_user(token)` מוכח בפועל שעובד עם publishable key בלבד
מול ה-API החי, לא רק בהנחה. הורץ ע"י המשתמש בטרמינל שלו (`getpass`, לא ע"י
קלוד — אותו אילוץ כמו checkpoint 7), עם סקריפט חד-פעמי מחוץ ל-repo. שני באגים
נמצאו ותוקנו תוך כדי הריצה בפועל: (1) ה-docstring הראשי נכתב כמחרוזת רגילה
במקום raw string — הנתיב `C:\Users\...` בתוכה נקרא כ-`\U` (unicode escape)
וגרם ל-`SyntaxError`; (2) `httpx.get` ללא `timeout` מפורש נכשל ב-`ReadTimeout`
מול cold start של Render (~50s, מתועד בסיכוני הפרויקט) — ברירת המחדל של
`httpx` היא 5 שניות בלבד. שניהם תוקנו (`r"""`, `timeout=60`) לפני ריצה מוצלחת.

### E-expired — token פג תוקף · checkpoint 15 · ⚠ **`waived` / `not feasible` — מגבלת פלטפורמה, לא כשל ביצוע** (הכרעת המשתמש, 03.09.2026 19:03 UTC)  *(D6)*

| תנאי | תוצאה צפויה | ראיה |
|---|---|---|
| הורדת JWT expiry למינימום → התחברות → המתנה מעבר לתוקף → `/api/me` | **401** | קוד סטטוס |
| שחזור הערך המקורי | הערך חזר | ערך לפני/אחרי + אימות-אחרי מפורש |

**מה נבדק בפועל, לפני שהוכרע לזנוח:** נבדקו שלושה מקומות ב-Supabase Dashboard
של הפרויקט (Free plan, `funneliq`) שבהם משך תוקף access token/JWT יכול
היה להיות:
1. Auth → **Sessions** — יש שם רק "Time-box user sessions" ו-"Inactivity
   timeout", **שניהם נעולים מאחורי Pro plan** ("Configuring user sessions is
   only available on the Pro Plan and above").
2. Sign In / Providers → **User Signups** — לא רלוונטי.
3. Sign In / Providers → **Email provider panel** — יש שם "Email OTP
   expiration" (3600s) — זה משך תוקף קוד/קישור אימות במייל, **לא** משך תוקף
   של ה-access token עצמו. הגדרה נפרדת לחלוטין (תואם `otp_expiry` מול
   `jwt_expiry` הנפרדים ב-`config.toml`).

תיעוד Supabase הרשמי (`docs/guides/auth/sessions`) מפנה במפורש ל-Auth
settings → Sessions כמקום להגדרת JWT expiry, אבל זה לא תואם את מה שנצפה
בפועל ב-Dashboard של הפרויקט הזה — כנראה שהתיעוד מיושן ביחס ל-UI הנוכחי, או
שההגדרה הועברה מאחורי Pro plan מבלי שהתיעוד עודכן.

**ההכרעה:** לוותר על `E-expired` כפי שתוכנן. **קריטריון הקבלה `401` על token
פג תוקף (§ז) נשאר לא-מכוסה בראיה חיה**, מתועד כמגבלת פלטפורמה (Free plan) ולא
כפער ביצוע — ההתנהגות עצמה (`current_user` מטפל בטוקן שנדחה כ-`401`) כבר
מכוסה ב-E-local דרך mock. אפשרויות שנשקלו ונדחו: Management API עם Personal
Access Token ברמת חשבון (סוג מפתח חדש שלא נכנס לפרויקט עד כה) · שדרוג זמני
ל-Pro plan (עלות כסף אמיתית).

### E-secrets — היגיינת סודות · checkpoint 8 ✅ (טענה 1) + checkpoint 15 ✅ (טענה 2, 03.09.2026)  *(B7)*

שתי טענות **נפרדות**, ואין לערבב ביניהן — ולכן שני checkpoints שונים:

| טענה | מוכיחה | אינה מוכיחה |
|---|---|---|
| **1. `.env` מוחרג ואינו tracked** (checkpoint 8, מקומי בלבד). ✅ **בוצע 03.09.2026:** `git check-ignore -v .env` → `.gitignore:2`; `git ls-files --error-unmatch .env` → נכשל | שהקובץ לא ייכנס ל-commit | ❌ שום דבר על מה שהודפס לפלטים, ל-PR או ל-CI |
| **2. אף ערך רגיש לא הופיע בתוכן שנשמר** (checkpoint 15). ✅ **בוצע 03.09.2026:** סריקת דפוסים (`sb_secret_`, `eyJhbGciOi`) על עץ העבודה, כל היסטוריית הגיט (כל הענפים), גוף+תגובות `PR #14` | שהערכים לא דלפו | 4 התאמות בעץ העבודה — כולן תיעוד/regex (`sb_secret_…`), לא ערך אמיתי. 16 התאמות בהיסטוריה — כולן `sb_secret_should_never_appear` (הסנטינל מ-`test_config.py`). `PR #14` — אפס התאמות |

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
| `E-secrets` טענה 1 | 8 | ✅ `.env` מוחרג ואינו tracked |
| E-deploy | 14 | ✅ `6/6 true` (§ה E-deploy) |
| E-live | 15 | ✅ `4/4` — D8-b נסגר |
| E-expired | 15 | ⚠ **`waived` / `not feasible`** — מגבלת Free plan, ר' §ה |
| E-cdn-fail | 15 | ✅ הודעה בעברית, `#loading` מוסתר |
| E-browser | 15 | ✅ login/refresh/sign-out אומתו; `demo-noorg` מכוסה ב-E-live |
| `E-secrets` טענה 2 | 15 | ✅ נקי — רק סנטינל בדיקה |

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
| 9 | סגירת ביקורת נוספת על התכנון | תשתית (תהליכי — סוגר את שער התכנון, לא קריטריון מוצר) | — | ביקורת עצמאית של **בעל הפרויקט** (לא הרצת כלי Codex) על `PHASE4.md` מול `ROADMAP.html` — **תוצאה: `blocker: none`, `important: none`, `cosmetic: none`**. פרוט מלא ב-§טו סעיף 7 | ✅ **done, 03.09.2026 14:58 UTC** |
| 10 | יישום תיקונים אם יידרשו מ-9 + `pytest -q` מלא מחדש | תלוי בממצאי 9 — **9 סגר blocker:none / important:none / cosmetic:none, אין תיקון ליישם** | checkpoint 9 | `pytest -q` → `33 passed` | ✅ **done, 03.09.2026 15:07 UTC** |
| 11 | (1) `git commit` → (2) `git push` על `feat/auth` → (3) פתיחת PR → (4) CI ירוק | CI ירוק בלי credentials | checkpoint 10 | commit `9a1d7cc`; PR #14; שתי ריצות CI success (push 33771862855, pull_request 33771886042) | ✅ **done, 03.09.2026 15:20 UTC** |
| 12 | אישור ומיזוג ל-`main` | תשתית (מאפשר 13–16; אישור נפרד, בלתי הפיך) | checkpoint 11, CI ירוק | `PR #14` מוזג — merge commit `91e822f`; CI על `main` success (run `33774408897`); `origin/main` מאומת = `91e822f` | ✅ **done, 03.09.2026 15:45 UTC** |
| 13 | Render: `SUPABASE_URL`+`SUPABASE_PUBLISHABLE_KEY` (בלי secret) + redeploy | תשתית ל-14 | checkpoint 12 ✅ | המשתמש הגדיר בפועל ב-Render Dashboard; סטטוס Live; `/api/config` → `200` עם הערכים הנכונים (לא `500`) | ✅ **done, 03.09.2026 16:08 UTC** |
| 14 | אימות `/health`+`/api/config` חי — **E-deploy** | `/api/config` ציבורי חי; Render מדבר עם הפרויקט הנכון (C3) | checkpoint 13 | פקודת E-deploy (§ה) הורצה — 6/6 `true`: `http_200`, `json_valid`, `fields_exactly_two`, `key_is_publishable`, `no_secret_marker`, `url_matches_project`. `/health` → `200`. בלי הדפסת ערכים | ✅ **done, 03.09.2026 16:11 UTC** |
| 15 | **E-live**(D8-b)·**E-expired**(D6)·**E-browser**·**E-cdn-fail**·`E-secrets` טענה 2 | `401`/`403` חי; token פג; session/sign-out; RTL; כשל CDN בעברית; אין סוד בגיט/PR/CI | checkpoint 14 | **checkpoint 15 כולל 5 קבוצות ראיה נפרדות — 4/5 הושלמו: E-live ✅, E-cdn-fail ✅, E-browser ✅, `E-secrets` טענה 2 ✅. E-expired = `waived`/`not feasible`** (מגבלת Free plan, הכרעת המשתמש 03.09.2026 19:03 UTC) — לא ⏳, אין עוד המתנה לו, ואינו נכשל. **תוספת 03.09.2026 19:24 UTC:** בעקבות חשיפת טוקן ב-E-browser (ר' שם) נבדק ב-SQL קריאה-בלבד שאין sessions/refresh tokens פעילים ל-`demo-northbound` — הסקה ממצב ה-DB, לא בדיקת 401 ישירה על הטוקן החשוף עצמו | ✅ **done, 03.09.2026 19:24 UTC** (4/5 בוצעו, 1/5 `waived`/`not feasible` בהכרעה מתועדת — לא נותר פריט תלוי) |
| 16 | מסירת פרטי שני משתמשי הדמו למרצה + סגירה | פרטי הדמו נמסרו למרצה | checkpoint 15 | אישור המשתמש | ⏳ not_started |

**תלויות:** 12 לפני 13 — קוד פאזה 4 חייב להיות ב-`main` לפני שהוא רלוונטי
ל-Render, ש-`render.yaml` מגדיר לפרוס מ-`branch: main`. **אומת אמפירית
03.09.2026:** לפני שקוד פאזה 4 היה ב-`main`, `/api/config` על השירות החי
החזיר `404` (ה-route לא קיים בקוד הפרוס) — לא `500` (env חסר). הגדרת env vars
לפני מיזוג הייתה תקינה אך לא ניתנת לאימות. 13 לפני 14, 14 לפני 15.

**checkpoint 13 מוכן — בייסליין נבדק אמפירית מיד אחרי checkpoint 12 (03.09.2026
15:5X UTC):** `autoDeployTrigger: commit` ב-`render.yaml` כבר הפעיל redeploy
אוטומטי מהמיזוג עצמו, בלי פעולה נוספת. `GET /health` → `200` (0.14s, חם).
`GET /api/config` → **`500` `{"detail":"Supabase configuration missing"}`** —
לא `404` יותר: ה-route קיים, הקוד חי, חסרים רק ערכי משתני הסביבה (בדיוק
ההתנהגות שתוכננה ב-D10 — נכשל רועש, לא שקט). `GET /` → `200`, מסך הלוגין
מוגש.

**✅ אומת בפועל 03.09.2026 16:08 UTC, לא הנחה:** המשתמש הגדיר את שני משתני
הסביבה ב-Render Dashboard ושמר. **"redeploy" כפעולה נפרדת לא נדרשה** — Render
הפעיל restart אוטומטי משמירת המשתנים בלבד, בלי "Manual Deploy". סטטוס חזר
ל-Live, ואז: `GET /health` → `200`. `GET /api/config` → **`200`**
(לא `500` יותר), עם `supabase_url` ו-`supabase_publishable_key` תואמים בדיוק
לערכים שהוזנו. זו ראיה ישירה ל-checkpoint 13, לא לבדיקה המובנית של
checkpoint 14 (בדיוק שני שדות, פורמט מפתח, היעדר secret marker) — זו עדיין
נפרדת ולא בוצעה.
**checkpoint 16 (האחרון) דורש אישור נפרד** (8–15 בוצעו — ר' §יד לתיעוד
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
| מסך התחברות עברי RTL, נגיש במקלדת | E-browser | ✅ **נסגר** |
| הרשמה ציבורית כבויה | F1 | ✅ |
| שני משתמשי דמו מאומתים מראש, `app_metadata` נכון | SQL, checkpoint 7 | ✅ |
| `401` בלי token / עם token שנדחה | E-local + E-live | ✅ **נסגר** (E-local 33/33 + E-live חי) |
| `403` עם token בלי הרשאה | E-local + E-live | ✅ **נסגר** (E-local 33/33 + E-live חי) |
| **שגיאת קונפיגורציה או תשתית אינה מוחזרת כ-`401`** (D7א) | E-local | ✅ **חדש, נסגר** — 6 מקרים |
| `401` על token פג תוקף | E-expired | ⚠ **`waived` / `not feasible` — מגבלת פלטפורמה (Free plan), לא כשל ביצוע.** ההתנהגות מכוסה ב-mock (E-local) בלבד — **אין ראיה חיה של 401 על טוקן שפג בפועל** |
| session שורד רענון · sign-out מנקה | E-browser | ✅ **נסגר** |
| **כשל טעינת `supabase-js` מוצג כשגיאה בעברית, לא כ-loading אינסופי** | E-cdn-fail | ✅ **נסגר** — קוד תוקן ב-7א, נבדק בפועל בדפדפן ב-15 |
| **ה-SRI המקובע תואם לקובץ שב-CDN** | E-sri | ✅ **חדש, נסגר** |
| `/api/config` ציבורי, שני שדות, בלי secret ובלי מידע עסקי | E-local + E-deploy | ✅ **נסגר** |
| **ה-Render הפרוס מדבר עם פרויקט Supabase הנכון** (C3) | E-deploy | ✅ **נסגר** |
| CI ירוק בלי credentials | checkpoint 11 | ⏳ |
| `.env` מוחרג ואינו tracked | E-secrets, טענה 1 | ✅ |
| **אף ערך רגיש לא הופיע בגיט, ב-PR או ב-CI** | E-secrets, טענה 2 | ✅ **נסגר** |
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
| JWT expiry לא הוחזר אחרי E-expired | אימות-אחרי מפורש בתוך checkpoint 15 | **מבוטל** — E-expired `waived`/`not feasible`; JWT expiry מעולם לא שונה, אין מה לשחזר |
| טוקן/סיסמה נשפכים לראיה | D15 + E-secrets טענה 2 + כלל "שמות מפתחות בלבד" ב-E-browser | ⚠ **קרה בפועל** — צילום מסך חשף `access_token`/`refresh_token` חיים של `demo-northbound` ב-E-browser (03.09.2026). מוצג ולא הועתק/נעשה בו שימוש. מוגן ע"י sign-out + אימות SQL קריאה-בלבד ש-0 sessions/refresh tokens פעילים נותרו (19:24 UTC) — הסקה ממצב DB, לא בדיקת 401 ישירה על הטוקן עצמו (D15 אוסר החזקתו) |
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
| `render.yaml` | אין `envVars` | ✅ תוקן — `sync: false` לשני השדות, בלי ערכים, `SUPABASE_SECRET_KEY` נעדר במפורש. נדחף ב-commit `9a1d7cc` (checkpoint 11), עדיין רק ב-`feat/auth` — יגיע בפועל ל-`main` ולפריסה החיה רק אחרי checkpoint 12 (מיזוג) |
| `SPEC.md` §Auth | **אומת ישירות 03.09.2026 — עדיין לא תוקן.** `SPEC.md:1068-1073`
("### שער החלטה לפני פאזה 4 — מסירת גישת הדמו") עדיין מנוסח כהכרעה עתידית
פתוחה ("לפני תחילת ביצוע פאזה 4 **חייבת להיסגר**..."; "**אין לנחש** או לקבע
מראש..."), למרות שההכרעה (D1: שני משתמשי דמו — `demo-northbound` עם
`organization=northbound`, `demo-noorg` בלעדיו — המשתמש מוסר את הפרטים
בעצמו) כבר נפלה ומומשה. חסר: משפט סגירה בסוף אותו סעיף ב-`SPEC.md` שמצטט את
D1 ומפנה ל-`codex-review.md`/`PHASE4.md`. | ⏳ **פתוח** |
| `ROADMAP.html` | פריט checkpoint 7א | ✅ נוסף, מסומן `done` עם ראיה |

---

## יא. מעמד המסמך

המשתמש אישר ביצוע פאזה 4 בהיקף מוגבל, checkpoint אחר checkpoint, ולא אישור
גורף. checkpoint 7א בוצע 03.09.2026 04:09 UTC (§ה, §ו). **checkpoint 8 ואילך
ממתין לאישור נפרד** — לא ניתן אישור גורף לשאר הפאזה.

---

## יב. מה נדרש לפני סגירה

1. checkpoint 16 (§ו) — 9–15 בוצעו (15 עם E-expired נזנח בהכרעה מתועדת).
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
התכנון בלבד, ואינו הוראת ביצוע ל-checkpoint 16 — זו נדרשת בנפרד.
