# מרשם דרישות הבריף — 74 דרישות אטומיות (B1–B66)

> **מקור אמת יחיד לדרישות `FunnelIQ_Assignment.html`.** כל שורה היא חובה אטומית אחת
> שחולצה מהבריף, עם ציטוט מילולי מלא, בעלים יחיד, תורמים, מאמת, סטטוס וראיה.
>
> נבנה ואומת כחלק מ"תוכנית היישור לבריף" ב-08–09.09.2026 (ר' `docs/planning/codex-review.md`
> ותכנון פאזה 8A). `tests/test_requirements_traceability.py` אוכף את שלמותו: כל `source_quote`
> חייב להימצא מילולית בטקסט הגלוי של הבריף, לכל דרישה יש בעלים יחיד, ולכל דרישה `done`
> יש ראיה. מזהה `B47` הוסר במפורש (סעיף אחרון) ואינו יתום — הוא לא נמחק בשתיקה.
>
> **מקרא סטטוס:** `done` בוצע ומאומת · `planned` בעלים ידוע, טרם בוצע · `gap` כתיבה,
> מימוש או הצדקה חסרים/לא תקפים · `N/A` אופציונלי בבריף ונדחה ביודעין · `parent` דרישת-על שאינה נסגרת
> עצמאית — ר' הילדים בעמודת הראיה.

## ביקורת רוחבית 10A — בביצוע, 11.09.2026

[PHASE10A.md](PHASE10A.md) מגדירה בדיקה חוזרת של כל 73 השורות מול הבריף והראיות,
במיוחד משמעות הקלט, מועד החיזוי, יחידות הרווח וההבדל בין API למסע משתמש.
המרשם הזה נשאר מקור העקיבות היחיד. תורם `10A` מציין נגיעה רוחבית בתוכנית
שאושרה לביצוע, לא השלמת הדרישה. CP0–CP3 נסגרו לאחר שביקורת הביניים נעלה את
אוכלוסיית B46b ל־`closed>0`; CP4 הושלם בארבעה חלקים A–D.

**CP1 נסגר ב־12.09.2026:** כל 73 השורות נקראו מול הציטוט בבריף והראיה בפועל.
שלושה סעיפי חשיפה (B28/B36/B52) הוחזרו ל־`planned`: ה־API החי נשמר כראיית
ביניים, אך אין עדיין מסע משתמש בדשבורד. חמישה סעיפים הוחזרו ל־`gap`:
B18/B22/B23/B24 חסרים תשובת כתיבה מלאה ב־FINDINGS. B63 חזרה ל־`done`
ב־CP2 לאחר שהוגדר תנאי שימוש שאינו טוען לחיזוי לפני רכישה: רוכש ידוע,
חלון גיוס חודשי סגור ומעקב 1 שהושלם, לצד גילוי שאין בקובץ ראיית זמן.
**תיקון ביקורת CP0–CP3, 12.09.2026:** שלושה סטטוסים שסומנו `done` הקדימו את
הראיה הכתובה. B31 טרם כוללת החלטה מנומקת אם טיפול באי־איזון מוצדק; B33 מכילה
ערך baseline בארטיפקט אך טרם דווחה לצד חמשת מדדי P3; B46b נשענת על
`purchased=1`, אף שנוסח הבריף "deals that eventually closed" עשוי לדרוש
`closed>0`. בקובץ יש 3,163 רשומות בראשונה ו־3,318 בשנייה, כולל 155 רשומות
`closed>0 AND purchased=0`. אוכלוסיית B46b ננעלה ל־`closed>0`; היא נשארת
`gap` עד כתיבת התשובה ב־CP4 ותיקון המימוש מתוכנן ב־CP6/CP9.
הספירה לאחר ביקורת CP0–CP3 הייתה 39 `done`, 15 `planned`, 17 `gap`, אחת
`N/A` ואחת `parent`. **עדכון CP4-A, 12.09.2026:** B31 נסגרה לאחר שנכתבה
הכרעה מנומקת נגד weighting במודל P3 הנפרס. B29b/B29c/B32/B33/B37a–d קיבלו
נוסחים וראיות מוכנים, אך נשארו `gap` עד הטמעה ב־REPORT כנדרש בתוצר הסופי.
**עדכון CP4-C, ‏12.09.2026:** B49 ו־B51 הוחזרו מ־`done` ל־`gap` לאחר
שבדיקת train-only הוכיחה שפרופילי החציון של P6 מפרים זהויות מקור בארבע מחמש
רמות התקציב. **עדכון CP4-D, ‏12.09.2026:** B46b נסגרה לאחר שנכתבה תשובה
מחייבת על אוכלוסיית `closed>0`: חציון 3, שכיח 2, ממוצע 3.706 ו־1,595/3,318
רשומות עם ממוצע 4+ שיחות. פער ה־API והארטיפקטים נשאר מתועד לתיקון CP9 ואינו
מבטל את השלמת דרישת הכתיבה שבבעלות פאזה 5. הספירה הפעילה: 39 `done`,
15 `planned`, 17 `gap`, אחת `N/A` ואחת `parent`.
שינוי סטטוס אינו מוחק את העבודה שכבר בוצעה; הוא מתקן מה עוד נדרש לסגירה.

**עדכון CP7, ‏12.09.2026:** המרשם סונכרן מול SPEC, חוזי המסך ומסמכי הפאזות.
לא נמצאה הצדקה לשינוי סטטוס נוסף: שלושת נתיבי החיזוי/סימולציה נשארים
`planned` עד חשיפה בדשבורד, B49/B51 נשארים `gap` עד תיקון P6, ו־B41 נשארת
`planned` עד פריסת CatBoost ל־P4S והצגתו. הספירה נשארת 39 `done`, ‏15
`planned`, ‏17 `gap`, אחת `N/A` ואחת `parent`.

**עדכון CP8, ‏12.09.2026:** נקבע מסלול סגירה לכל דרישה פתוחה בלי לשנות
סטטוס: CP9 של 10A מטפל ב־B49/B51 ובחסמי B41/B50/B52/B53a/B53b; פאזה 11
מממשת B10/B28/B36/B41/B45/B50/B52/B56 ותורמת ל־B55b/B59; פאזה 12
מאמתת את המסע החי ומספקת ראיית קבלה; ופאזה 13 משלימה את B1/B6/B18/
B22/B23/B24/B29b/B29c/B32/B33/B37a/B37b/B37c/B37d/B43/B53a/B53b/
B57/B60/B65 ואת רכיב התיעוד
של B59. ‏B54 נשארת parent ו־B58 נשארת N/A. הספירה אינה משתנה.

**עדכון CP9, ‏12.09.2026:** שלושת חסמי המימוש תוקנו. Follow-up קורא ומאמת
את אוכלוסיית `closed>0`; ‏P4S נפרס כ־CatBoost ייעודי מגרסת המקור `1c70ca8`
תוך שמירת תוצאות Logistic ההיסטוריות; ו־P6 נבנה מחדש מפרופיל train נצפה
ודטרמיניסטי בלי לפתוח שוב את ה־Holdout. ‏B49 ו־B51 נסגרו ל־`done`.
הספירה הפעילה: 41 `done`, ‏15 `planned`, ‏15 `gap`, אחת `N/A` ואחת `parent`.

**עדכון G2 (שער `10→11`), ‏14.09.2026:** מרשם 73 הדרישות נמצא לא-שלם —
§07 בבריף מונה שבעה סעיפים, ורק ששה היו ממופים (`B60`–`B65`). הסעיף *"Use
AI tools if you like — but understand what you ship. The point is to be
able to explain every line, because that's what makes it yours"* לא הופיע
במרשם כלל. נוספה שורה חדשה, `B66`, בעלים 13, תורמים `כולן`, סטטוס
`planned`. במקביל תוקנה עמודת `contributors` ב-11 שורות: הוסר מ-`B33`
(אוסר הצגת ה-majority baseline לפי `IA.md` §3.4, ולכן פאזה 11 אינה תורמת
לו), ונוסף ל-`B24`/`B29c`/`B42`/`B43`/`B46a`/`B46b`/`B46c`/`B53a`/`B53b`/`B65`
— פאזה 11 מרנדרת בפועל את תוכנן, גם אם אינה סוגרת אותן.
⛔ אפס שינוי ב-`owner`/`status`/`evidence` של שורות קיימות. הספירה הפעילה:
41 `done`, ‏16 `planned`, ‏15 `gap`, אחת `N/A` ואחת `parent` — **74** בסך הכול.

**עדכון שער `11→12` (סבב תיקון אחרי 11A), ‏22.09.2026 — טיוטה הממתינה
לביקורת ולאישור:** ⛔ **אפס שינוי `status`** ואפס שינוי `source_quote`;
הספירה נשארת 41 `done`, ‏16 `planned`, ‏15 `gap`, אחת `N/A` ואחת `parent`.
תוקן `evidence` שהתיישן: `B55b` (הנוסח "התוכן והמימוש החי טרם קיימים"
אינו נכון אחרי פאזה 11 ו-11A — מה שחסר הוא ראיית קבלה, לא מימוש), `B10`
(ספירת "35/35" ספרה פונקציות כמקרים), `B56` (תאריך אימות הפריסה),
ו-`B59` (רכיב המסע חודד). **מיפוי עשר השורות שפאזה 12 מאמתת**, כפי
שנקבע ב-`PHASE12.md` §ו ובהכרעות המתוקנות שם:

- `B10`/`B56` ⇒ `done` על ראיית **CP2** (session ושער ההתחברות החיים).
- `B45`/`B50`/`B28`/`B36`/`B41`/`B52` ⇒ `done` על ראיית **CP4** (חשיפה
  בדשבורד החי), כולל שער `P12-D9` ל-`B45`/`B50`.
- `B55b` ⇒ `done` על **CP4 + מסע CP7**, ורק כאשר כל **חמש** שאלות
  המייסדת קיבלו תשובה מנוסחת על הגרסה החיה — כולל שהבוחן **קרא בפועל**
  את בלוקי ההמלצה, ⛔ לא רק שהמספרים הוצגו.
- ⚠ CP7 (מסע הבוחן החיצוני, `P12-D10`) הוא תנאי לסגירת **הפאזה**, ⛔ אך
  אינו תנאי לכל שורה: כשל CP7 אינו מוחק ראיית CP2/CP4 שנאספה, אלא מותיר
  את הפאזה פתוחה.
- `B59` ⇒ נשארת `planned` גם אחרי מסע מוצלח; רכיב התיעוד (`README.md`)
  בבעלות פאזה 13.
- ⚠ ל-`B45`/`B50`/`B28`/`B36`/`B41`/`B52` חל בנוסף שער `P12-D9`: הנוסח
  הקנוני של `DESIGN.md` §6.1 חייב להופיע במסלול **הבריא** עם הערכים
  החיים, בראיה חיובית — ⛔ היעדר נוסחי §6.1ג אינו ראיה מספקת.

## §04 GitHub

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B1** | §04 | "A public repository with a clear, professional README.md (project overview, architecture diagram or description, local setup steps, and the live URL)." | `README.md` קיים ומכיל סקירה, ארכיטקטורה, התקנה מקומית ו-URL חי | 13 | 1 | 12 | planned | הקובץ אינו קיים (אומת) |
| **B2** | §04 | "A meaningful commit history — small, descriptive commits, not one giant "final" dump." | היסטוריית commits קטנים ותיאוריים | 1 | כולן | 12 | done | `git log`; 8 PR ממוזגים #14–#21 |
| **B3** | §04 | "Use feature branches and open at least one Pull Request (even solo — it shows you know the workflow)." | feature branch + לפחות PR אחד | 1 | כולן | 12 | done | PR #14–#21 |
| **B4** | §04 | "A .gitignore that keeps secrets, data dumps, and virtual-environments out of the repo. No API keys or .env files may ever be committed." | `.gitignore` מוציא secrets, data ו-venvs | 1 | — | 12 | done | `.gitignore` — `.env`, `.env.*`, `funnel_marketing_data.csv`, `venv/`, `.venv/` |
| **B5** | §04 | "A working GitHub Actions workflow that runs on every push (at minimum: install dependencies and run your tests/lint)." | workflow בכל push שמריץ תלויות ובדיקות | 1 | — | 12 | done | `.github/workflows/ci.yml` — `on: [push, pull_request]`, `pip install -r requirements.txt`, `python -m pytest -q` |

## §04 Supabase — נתונים

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B6** | §04 | "Provision a Supabase project and design a table (or tables) for the dataset. Include a schema file (schema.sql) in the repo." | קובץ `schema.sql` ב-repo | 13 | 3 | 12 | planned | generated snapshot מהמיגרציות + בדיקת parity; ⛔ ללא symlink, ללא שינוי DB, ללא פתיחת פאזה 3 |
| **B7** | §04 | "Load the CSV into the database with a repeatable script — not by hand." | טעינת CSV בסקריפט חוזר | 3 | — | 12 | done | `scripts/load_data.py` — upsert idempotent |
| **B8** | §04 | "Your application must read from Supabase at runtime (for at least one feature, e.g. serving historical records or computing insights), using credentials from environment variables." | קריאה מ-Supabase בזמן ריצה עם credentials מ-env | 9 | 3 | 12 | done | `/api/insights/followup`, `/api/insights/budget-tiers` ממומשים (`docs/planning/PHASE9.md` checkpoints 8–9). **ראיה חיה בוצעה** (ק' 72–73, 2026-09-10, מול `https://funneliq.onrender.com` אחרי מיזוג `b176eab`): `demo-northbound` → 200 (`budget-tiers` rows=3; `followup` stages=5, population_n=3163); טוקן לא תקין → 401; `demo-noorg` → 403. status codes בלבד, ר' PHASE9.md §8/checkpoint 11 |
| **B12** | §04 | "Tie it together with access control: enable Row Level Security and write policies so the database itself enforces that only authenticated users can read the data. For RLS to actually matter, user-facing reads should reach Supabase with the signed-in user's access token (or your API verifies the user's JWT before serving) — a backend that reads everything with the service key bypasses your policies." | RLS + policies, וקריאות המשתמש נושאות את הטוקן שלו | 9 | 3 | 12 | done | policy `funnel_records_northbound_select`; views `security_invoker=true`; `app/supabase_client.py` — לקוח פר-בקשה עם JWT המשתמש (D4, checkpoint 7). **ראיה חיה בוצעה** (ק' 72–73, 2026-09-10, מול Render אחרי מיזוג `b176eab`): `demo-northbound` (מסונף ל-`northbound`) → 200 עם שורות אמיתיות; `demo-noorg` (ללא ארגון) → 403 — RLS/JWT נאכפים בפועל בפרודקשן, לא רק ב-Mock |

## §04 Supabase — אימות

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B9** | §04 | "Build a login screen using Supabase Auth (email + password at minimum)." | מסך התחברות email+password | 4 | — | 12 | done | `app/static/index.html` + `app.js`; 11 בדיקות ב-`test_auth.py` |
| **B10** | §04 | "Handle the session properly: an unauthenticated visitor sees only the login screen; a signed-in user reaches the dashboard and predictions; sign-out works and clears the session." | ניהול session מלא כולל גישה לדשבורד ולחיזויים | 11 | 4, 10, 10A | 12 | planned | פאזה 11 (CP1, מוזגה ב-`c182b4b`) מימשה את שלושת חלקי הסעיף: מבקר לא מאומת רואה **רק** Login (ה-shell חסום עד `200` מ-`/api/me`); משתמש מחובר מגיע לדשבורד ולחמשת המסכים דרך hash router; `sign-out` מנקה session ומעלה epoch (`P11-D14`). שבעת ענפי ה-bootstrap (`P11-D13`) מובחנים. ראיה: מקרי הפרכה 6/7/8/9/9א–9ו/10/11/12 ב-`e2e/` (CP11) + `docs/design/states/bootstrap-*.jpg` (CP12). ⚠ **תיקון ספירה, 22.09.2026:** הנוסח הקודם כאן ("35/35") ספר פונקציות כמקרים — `PHASE11A.md:27` קובע 30 מקרי הפרכה ב-32 פונקציות + 3 בדיקות תשתית = 35 פונקציות; כיום `e2e/` מכסה 46 מקרים (30 + 16 של 11A) ב-67 פונקציות. ⛔ חסר לסגירה: ראיית קבלה חיה מול הפריסה — מסע התחברות/יציאה אמיתי מול Supabase, ומסע בוחן חיצוני (`P12-D10`), בבעלות פאזה 12 |
| **B11** | §04 | "Use the public anon key in the browser for the login flow — never expose the service key client-side. Keep any privileged operations server-side." | anon בדפדפן, service לעולם לא בצד לקוח | 4 | 9 | 12 | done | `test_config.py` — `"sb_secret" not in response.text`; `render.yaml` ללא `SUPABASE_SECRET_KEY` |

## §04 פריסה

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B13** | §04 | "Deploy your service to Railway so it's reachable at a public URL." | השירות זמין ב-URL ציבורי | 2 | — | 12 | done | Render לפי B64; `https://funneliq.onrender.com/health` החזיר 200 בבדיקות פאזה 2 ופאזה 9 |
| **B14** | §04 | "Secrets (Supabase keys, config) are set as Railway environment variables, never hard-coded." | secrets כמשתני סביבה | 2 | — | 12 | done | `render.yaml` `sync:false` לשני שדות בלבד |
| **B15** | §04 | "Connect the Railway service to your GitHub repo so pushes trigger a redeploy." | push מפעיל redeploy | 2 | — | 12 | done | `render.yaml`: `autoDeployTrigger: commit`, `branch: main`; `PHASE2.md` §ג — מיזוג PR #7 יצר deploy אוטומטי ל־`9d7a975` |
| **B16** | §04 | "Expose a health-check endpoint and confirm the deployment survives a restart." | health-check + שרידות restart | 2 | — | 12 | done | `/health` ב־`app/main.py`; `render.yaml` `healthCheckPath: /health`; `PHASE2.md` §ד — restart יזום וחזרה ל־200 לאחר כ־7 שניות |

## §05 חבילה 1

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B17** | §05.1 | "a short written findings note (in the README or a /docs file)" | מסמך ממצאים כתוב | 5 | 13, 10A | 12 | done | `docs/FINDINGS.md` |
| **B18** | §05.1 | "covering missing-value handling" | טיפול בערכים חסרים מתועד | 5 | 10A | 12 | gap | `findings.json.missing_values` מכיל 4/29/33; `FINDINGS.md` סופר חסרים אך אינו מסביר באופן מלא כיצד טופלו |
| **B19** | §05.1 | "a correlation analysis against cumulative_profit" | קורלציה מול `cumulative_profit` | 5 | 10A | 12 | done | `findings.json.correlations` — 17 עמודות |
| **B20** | §05.1 | "the shape of the ad_budget → num_leads relationship" | צורת הקשר תקציב→לידים | 5 | 10A | 12 | done | `findings.json.ad_budget_leads_curve` (16 רמות); `ad_budget_leads_curve.svg` |
| **B21** | §05.1 | "and conversion rate (closed / num_leads) across budget tiers — Low (≤1500), Mid (2000–5000), High (>5000)." | שיעור המרה לפי שלושת הטיירים | 5 | 9, 10, 11, 10A | 12 | done | `docs/findings.json.budget_tiers` — Low **0.04524** (4.5%, n=780) · Mid **0.08220** (8.2%, n=1,717) · High **0.05433** (5.4%, n=1,003) · gap n=0 |
| **B22** | §05.1 | "How many rows are incomplete, and how did you handle them?" | תשובה כתובה | 5 | 13, 10A | 12 | gap | `FINDINGS.md` מציין 33 שורות לא־שלמות, אך תשובת הטיפול הכללית חסרה |
| **B23** | §05.1 | "Does more budget buy proportionally more leads, or do you see diminishing returns?" | תשובה כתובה | 5 | 13, 10A | 12 | gap | העקומה קיימת ב־`ad_budget_leads_curve.svg`; `FINDINGS.md` מתאר אותה אך נמנע ממסקנת proportional/diminishing returns |
| **B24** | §05.1 | "Which budget tier converts best — and does that surprise you?" | תשובה כתובה | 5 | 10, 11, 13, 10A | 12 | gap | `FINDINGS.md` מוכיח ש־Mid מוביל עם 8.2%; ההסבר האם ומדוע התוצאה מפתיעה חסר |

## §05 חבילה 2

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B25** | §05.2 | "three trained models — XGBoost, LightGBM, and CatBoost" | שלושת המודלים אומנו | 6 | — | 12 | done | `metrics.json.P2_selection.eligible = [catboost, lightgbm, xgboost]` |
| **B26** | §05.2 | "compared with 5-fold cross-validation on RMSE and R²" | השוואה ב-5-fold CV על RMSE ו-R² | 6 | — | 12 | done | `metrics.json.P2` — `mean_rmse`, `mean_r2` לכל אלגוריתם |
| **B27** | §05.2 | "Extract and compare feature importances across all three." | חילוץ importance לשלושת המודלים | 6 | 13 | 12 | done | `docs/feature_importance_P2.svg` + `metrics.json.global_feature_importance.P2` — אומת: `catboost`, `lightgbm`, `xgboost` |
| **B28** | §05.2 | "Expose the prediction through your app." | חשיפת חיזוי ה-LTV באפליקציה | 9 | 10, 11, 10A | 12 | planned | ראיית ביניים נשמרת: `/api/predict/ltv` חי ומאומת מול הארטיפקט ו־JWT (PHASE9 ק' 75). 10A/CP5 נעל זרימת קלט עצמאית/דוגמה; CP6 מיפה את התוצאה ל־`LtvPrediction.point_estimate/lower_bound/upper_bound` ואת OOD ל־`in_training_domain/warnings[]`. **המימוש בוצע בפאזה 11** (CP4/CP5, פאנל P2 בטופס המשותף, כולל OOD פר-פאנל וכשל חלקי; מקרי הפרכה 14/15). ⛔ נשאר המסע החי בפאזה 12 |
| **B29a** | §05.2 | "Should cumulative_profit be a feature here? Justify it." | הצדקה כתובה להחרגת `cumulative_profit` מ-P2 | 5 | 6, 13, 10A | 12 | done | `docs/planning/PHASE5.md` D2 · `docs/feature_matrix.md:66` — `Excluded` ב-P2/P3/P4, *"תוצאה מאוחרת/מצטברת… ברשימת הדליפה המפורשת בכולן"* · commit `339736b` — *"feat(phase5): checkpoint 6 — app/features.py, feature_matrix.md, test_features.py"* |
| **B29b** | §05.2 | "Which features dominate, and do the three models agree?" | השוואה כתובה בין שלושת המודלים | 13 | 6, 10A | 12 | gap | נוסח מאומת הוכן ב־`SPEC.md` §ראיות ותשובות CP4-A: `calls_to_closed` ראשון בשלושתם; יחידות importance אינן בנות־השוואה. חסרה הטמעה ב־REPORT |
| **B29c** | §05.2 | "In two sentences, what's the strongest lever on customer longevity, and what should Northbound do about it?" | שני משפטים: מנוף + המלצה | 13 | 6, 10, 11, 10A | 12 | gap | שני המשפטים הוכנו ב־`SPEC.md` §ראיות ותשובות CP4-A. CP6 קבע שנכס התצוגה ישמור `ltv.rank_1_by_algorithm` לכל שלושת המודלים ויפיק `ltv.dominant_feature` רק אם שלושתם זהים, עם גיבובי CSV ו־metrics; הנכס נוצר ב־CP9 ומכיל את שלושת הדירוגים וגיבוב metrics; נותרה הטמעה ב־REPORT/ממשק בפאזות 13/11 |

## §05 חבילה 3

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B30** | §05.3 | "three classifiers with 5-fold stratified CV" | שלושה מסווגים ב-CV מרובד | 6 | — | 12 | done | `metrics.json.P3_selection.eligible = [catboost, lightgbm, xgboost]`; `metrics.json.P3` עם `fold_scores` בני 5 |
| **B31** | §05.3 | "Check the class balance first and decide whether class-imbalance handling (e.g. scale_pos_weight or class weights) is warranted — justify either way." | בדיקת איזון + החלטה מנומקת | 6 | 13, 10A | 12 | done | `SPEC.md` §ראיות ותשובות CP4-A: 46.35%/53.65%, יחס משקל ≈1.16; ב־XGBoost הנפרס weighting הוריד ROC-AUC ‏0.79357→0.79281, ולכן אינו מוצדק |
| **B32** | §05.3 | "Report Accuracy, Precision, Recall, F1 and ROC-AUC, alongside the majority-class baseline." | דיווח חמשת המדדים | 13 | 6, 10A | 12 | gap | טבלת חמשת המדדים מול baseline הוכנה ב־`SPEC.md` §ראיות ותשובות CP4-A; חסרה הטמעה בחבילת הדוח הסופית |
| **B33** | §05.3 | "alongside the majority-class baseline" | דיווח מול baseline הרוב | 6 | 13, 10A | 12 | gap | baseline רוב באותו Holdout חושב כ־53.71% ונכתב לצד חמשת המדדים ב־`SPEC.md` §CP4-A; נשאר gap עד הטמעה בפועל ב־REPORT לצד B32 |
| **B34** | §05.3 | "Plot importances for your best model." | גרף importance למנצח | 6 | 13, 10A | 12 | done | `docs/feature_importance_P3.svg` |
| **B35** | §05.3 | "Design a simple business rule (e.g. "if LTV > X and CAC < Y, flag for outreach") and compare it against your model's predictions" | כלל עסקי + השוואה למודל | 6 | 13, 10A | 12 | done | `metrics.json.P3_manual_rules` — `ltv_months>23.0`, `cac<1000.0` |
| **B36** | §02 | "Each answer must be reachable through your deployed, signed-in application — not just printed once in a notebook cell." | חיזוי ה-upsell נגיש דרך האפליקציה | 9 | 10, 11, 10A | 12 | planned | ראיית ביניים נשמרת: `/api/predict/upsell` חי ומאומת עם JWT (PHASE9 ק' 75). 10A/CP6 מיפה את הפלט העסקי ל־`event_probability/base_rate/propensity_band` והוציא Accuracy/Precision/Recall שאינם בחוזה הדפדפן; **החשיפה בוצעה בפאזה 11** (CP5, פאנל P3 עם `summary-recommendation`, תג כיול ו-`model-details` מתקפל). ⛔ נשאר המסע החי בפאזה 12 — הסעיף דורש במפורש נגישות דרך היישום הפרוס והמחובר |
| **B37a** | §05.3 | "Is accuracy a sufficient metric here?" | תשובה כתובה | 13 | 6, 10A | 12 | gap | תשובה מאומתת ב־`SPEC.md` §CP4-A: לא; baseline משיג 53.71% ואינו מזהה חיובי. חסרה הטמעה ב־REPORT |
| **B37b** | §05.3 | "What does the majority-class baseline score, and how much does your model add?" | תשובה כתובה | 13 | 6, 10A | 12 | gap | `SPEC.md` §CP4-A: ‏53.71% מול 76.15%, תוספת 22.43 נקודות אחוז; חסרה הטמעה ב־REPORT |
| **B37c** | §05.3 | "Is upsell driven by one feature or a combination?" | תשובה כתובה | 13 | 6, 10A | 12 | gap | `SPEC.md` §CP4-A: `calls_to_closed` דומיננטי, CAC שני ותרומות קטנות נוספות; חסרה הטמעה ב־REPORT |
| **B37d** | §05.3 | "where does the rule win or lose?" | תשובה כתובה | 13 | 6, 10A | 12 | gap | `SPEC.md` §CP4-A: כלל הבריף פשוט ו־Precision=72.33% אך Recall=27.08% ואינו זמין בזמן; הכלל התפעולי Recall=12.47%; חסרה הטמעה ב־REPORT |

## §05 חבילה 4

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B38** | §05.4 | "Build: a CatBoost classifier" | מסווג CatBoost נבנה | 6 | 13, 10A | 12 | done | `PHASE6.md:693–695` — *"P4 — הזוכה Logistic (זכאי, מנצח CatBoost בפשטות)"*; `metrics.json.P4_selection`; One-SE + RSS ב-`train.py:1196`, לפני ה-Holdout |
| **B39** | §05.4 | "engineer a categorical budget-tier feature (Low/Mid/High) and let CatBoost handle it natively" | `budget_tier` בטיפול נייטיב | 6 | 10A | 12 | done | `train.py:243` `build_preprocessing_steps(encode_budget_tier=False)` |
| **B40** | §05.4 | "with hyperparameter tuning (search over learning rate, depth, and iterations)" | כוונון שלושת הצירים | 6 | 10A | 12 | done | `train.py:526` `catboost_param_distributions()` |
| **B41** | §05.4 | "Then build a scoring pipeline: given a new customer's early funnel data, output a 0–100 likelihood of becoming a super customer, served by your app." | ציון 0–100 ללקוח-על, מוגש באפליקציה | 8A | 9, 10, 11, 10A | 12 | planned | CP9 פרס CatBoost ייעודי ליעד P4S עם ארבעת הקלטים: `P4S-catboost-20260912-1c70ca8`; ה־API מחזיר אותו באותה סכמה. Logistic נשמר להשוואה. **הציון 0–100 נחשף בפאזה 11** (CP6, מסך P4S עצמאי: ארבעה שדות, `Math.round(p*100)`, כרטיס הקשר עסקי, ⛔ בלי טווח/צביעה/`uncalibrated`; מקרי הפרכה 18/19 + `docs/design/states/p4s-*.jpg`). ⛔ נשאר אימות המסע החי בפאזה 12 |
| **B42** | §05.4 | "Profile the super customers (referred = Yes, upsell = 1, long tenure): what share of total profit do they represent, and what's their average acquisition cost?" | פרופיל: אחוז רווח + CAC | 6 | 10, 11, 13, 10A | 12 | done | `metrics.json.super_customer_profile` — n=529, 33.61% מהרווח, CAC 990.7 מול 1,437.5 (חיסכון 31.1%); CP9 הפיק העתק מצומצם וגרסאי ב־`app/static/business_facts.json` |
| **B43** | §05.4 | "How could Northbound spot them earlier?" | תשובה כתובה | 13 | 8A, 10, 11, 10A | 12 | gap | CP9 מדד CatBoost: Holdout ROC-AUC=0.8014, PR-AUC=0.3420 ו־Recall=0 בסף 0.5, חלש מ־Logistic ההיסטורי (0.8187/0.3779). לכן ארבעת האותות משמשים רק ציון רציף לבדיקה ידנית של רוכש ידוע לאחר מעקב 1 וסגירת החלון; נשארה הטמעה ב־REPORT בפאזה 13 |

## §05 חבילה 5

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B44** | §05.5 | "the dropout rate at each follow-up stage (followup_1→followup_5), visualized" | נשירה בכל שלב, ויזואלית | 5 | 9, 10, 11, 10A | 12 | done | `findings.json.funnel_dropoff` — 21.7/25.7/18.6/10.4/29.2%; `funnel_dropoff.svg` |
| **B45** | §05.5 | "plus a data-driven recommendation surfaced in the dashboard" | המלצה מוצגת בדשבורד | 11 | 5, 9, 10, 10A | 12 | planned | טקסט מ־`SPEC.md` §הכרעת CP4-D; CP5 נעל פעולה/מגבלה גלויות, ו־CP6 נעל שהמלצה משולבת תלויה בשני חלקי `FollowupResponse` התקינים וללא fallback קבוע. החשיפה בוצעה בפאזה 11 (CP8, `app/static/js/screens/followup.js`): פסקת המלצת CP4-D מוצגת מילה במילה, ורק כששני חלקי `FollowupResponse` תקינים — כשל חלקי מסתיר את ההמלצה המשולבת ⛔ בלי מספר שמור חלופי. ראיה: מקרה הפרכה 23 + `docs/design/states/followup-error.jpg`. ✅ **ראיית success שהייתה חסרה נוספה (11A checkpoint 10, 22.09.2026, ⛔ לא ראיה סופית):** `docs/design/states/followup-success.jpg` (`P11A-D11`, checkpoint 8, commit `a3455d0`) — רינדור אמיתי מציג את שני הבלוקים (נשירה + `calls_to_closed`) מאוכלסים ואת פסקת המלצת CP4-D המשולבת בפועל; ⛔ פסקת ההמלצה עצמה לא שונתה ב-11A (לא נפסלה, ר' לעיל). ⛔ חסר לסגירה: ראיית קבלה חיה, פאזה 12 |
| **B46a** | §05.5 | "At which stage does dropout behave unexpectedly?" | תשובה כתובה | 5 | 10, 11, 13, 10A | 12 | done | `funnel_dropoff.followup_4 = 0.10372` — הנמוך ביותר |
| **B46b** | §05.5 | "For deals that eventually closed, how many follow-ups did they typically take?" | תשובה כתובה | 5 | 10, 11, 13, 10A | 12 | done | `SPEC.md` §הכרעת CP4-D ו־`docs/findings.json.calls_to_closed`: באוכלוסיית `closed>0` ‏(3,318) החציון 3, השכיח 2, הממוצע 3.706 ו־1,595 (48.07%) עם ממוצע 4+; CP9 יישר את ה־API לאותה אוכלוסייה עם עימוד וספירה עצמאית |
| **B46c** | §05.5 | "Should Northbound change its follow-up policy — yes or no, and why?" | תשובה כתובה | 5 | 10, 11, 13, 10A | 12 | done | `SPEC.md` §הכרעת CP4-D ו־`FINDINGS.md` §מסקנת P5 — לא לעצירה אוטומטית; להמשיך מבוקר ולמדוד עלות ושיעור סגירה שולי |

## §05 חבילה 6

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B48** | §05.6 | "a model that predicts cumulative_profit" | מודל שמנבא רווח מצטבר | 6 | 10A | 12 | done | `models/P6.joblib` (linear); `metrics.json.P6_holdout` — mae 3,678.9, rmse 4,590.9, r2 0.7961 |
| **B49** | §05.6 | "used to simulate allocation strategies built from campaign sizes the data actually covers (₪500–₪20,000)" | סימולציה בטווח שהנתונים מכסים | 6 | 10A | 12 | done | CP9 בנה מחדש `models/P6_simulation.json` בחמש הרמות 500, 2000, 5000, 10000 ו־20000 ובארבע אסטרטגיות שסכומן 50,000; כל פרופיל מצביע ל־`profile_source_row_id` שנצפה ב־train |
| **B50** | §05.6 | "and a recommendation for which maximizes expected total profit" | המלצה איזו ממקסמת רווח | 11 | 6, 9, 10, 13, 10A | 12 | planned | ⚠ **ראיה נפסלה בביקורת קודקס, 19.09.2026** (סבב ביקורת רוחב על `6e36c17..af07d6f`): `budget.js`'s `buildD9` מדפיס את שורת התשובה הקנונית ("`100x500` מדורגת ראשונה מספרית… ובדיקת העבר של רמת 500…") גם כשהנכס `business_facts.json` אינו זמין, ומציג המלצת פיילוט מבוססת rank/overlap בלבד — בניגוד מילולי ל־`DESIGN.md:547-548` ("אין להחליפם בהמלצה לפי rank בלבד"). הראיה הקודמת (שתוארה כ"הציגה זאת בפועל" על בסיס CP7) התייחסה רק למסלול התקין. בטיפול ב-`docs/planning/PHASE11A.md` (`P11A-D6`, checkpoint 4); ⛔ `status` ללא שינוי. ✅ **ראיית יישום 11A מעודכנת (checkpoint 10, 22.09.2026, ⛔ לא ראיה סופית):** `buildD9()` ב-`budget.js` תוקן (checkpoint 4, commit `a3455d0`) — ה-`answer` הקנוני ('100×500 מדורגת ראשונה…') הועבר לתוך אותו gate כמו `meaning`/`action` ואינו מודפס עוד ללא תלות בזמינות הנכס; במצב מושפל אין עוד המלצת פיילוט מבוססת rank/overlap בלבד. ראיה: `e2e/test_06_budget_screen.py` (הראיה הישירה ל-`D6` -- fixture מושפל/תקין על `buildD9()` עצמה), `e2e/test_10_facts_validation.py` (fixture חלקי ותקין לוולידציית הנכס `budget_backtest`), `docs/design/states/budget-success.jpg` (`P11A-D11`, רינדור אמיתי של המסלול התקין). ⛔ חסר לסגירה גם: ראיית קבלה חיה, פאזה 12 |
| **B51** | §05.6 | "Your simulator only knows each campaign's budget, so decide how to fill in the other features (a typical funnel profile per budget level is one reasonable approach)." | החלטה מתועדת על מילוי הפיצ'רים | 6 | 10A | 12 | done | `scripts/train.py::compute_budget_profiles`: בכל תקציב נבחרת שורת train נצפית במינימום L1 מנורמל־IQR מחציוני הקבוצה, ללא היעד ועם `source_row_id` כשובר שוויון; `metrics.json.P6_profile_method` |
| **B52** | §05.6 | "Expose the simulator in your app." | חשיפת הסימולטור | 9 | 10, 11, 10A | 12 | planned | `/api/simulate/budget` מחזיר את `P6_simulation.json` המתוקן כלוקאפ GET ללא body; חוזה ה־API עבר בבדיקות. **הממשק נבנה בפאזה 11** (CP7, `screens/budget.js` — GET בלבד, ⛔ אפס קלט משתמש, גרף + fallback טבלאי; מקרי הפרכה 21/24). ⛔ נשאר אימות המסע החי בפאזה 12 |
| **B53a** | §05.6 | "Based on what your model learned about diminishing returns, does concentrating or spreading spend win?" | תשובה כתובה | 13 | 6, 10, 11, 10A | 12 | gap | CP9: `100x500` מדורגת ראשונה (789,594) ו־`25x2000` שנייה (530,953), אך הטווחים חופפים וה־backtest ברמת 500 רחוק מאוד מהתחזית. אין הוכחה שפיזור קיצוני מנצח; נשארה הטמעה ב־REPORT |
| **B53b** | §05.6 | "What would you tell the founder to do next month?" | תשובה כתובה | 13 | 6, 10, 11, 10A | 12 | gap | ההמלצה המתוקנת: לא להעביר 50,000 ש״ח ל־100 קמפיינים על סמך המודל; אם בוחנים אחת מארבע החלופות, לבצע פיילוט מוגבל בדפוס `25x2000` ולמדוד רווח מצטבר באותו אופק. נשארה הטמעה ב־REPORT |

## §06 מה תבנה

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B54** | §06 | "A public GitHub repository — code, README.md, schema.sql, a CI workflow, and a commit history that shows how you worked." | חבילת ה-repo | parent | — | — | parent | ⛔ אינו נסגר עצמאית → B1, B2, B5, B6 |
| **B55a** | §06 | "A live application URL on Railway — a real link you can share that actually answers the founder's questions." | URL ציבורי חי | 2 | — | 12 | done | `https://funneliq.onrender.com` חי; Render לפי B64; אימותים מתועדים ב־PHASE2 וב־PHASE9 |
| **B55b** | §06 | "A live application URL on Railway — a real link you can share that actually answers the founder's questions." | האפליקציה הפרוסה **עונה בפועל** לשאלות המייסדת | 12 | 9, 10, 11, 13, 10A | 12 | planned | ⚠ ה-URL חי (B55a). 10A/CP5 מיפה את חמש התשובות לכרטיסי יכולת גנריים בלי לחשוף את ניסוח המשימה. ⚠ **עודכן 22.09.2026 — הנוסח הקודם ("התוכן והמימוש החי טרם קיימים") התיישן:** פאזה 11 מימשה את חמשת המסכים ופאזה 11A יישרה אותם לחוזה התכן, ובבדיקת השער נמצא שהפריסה מגישה את build 11A בפועל (8/8 הנכסים ש-11A שינתה — זהים ל-blob שלהם ב-`HEAD`). מה שחסר אינו המימוש אלא **ראיית הקבלה**: אף אחד עדיין לא קיבל מהגרסה החיה, בהתחברות אמיתית, תשובה מנוסחת לכל חמש השאלות. סגירה ⇐ CP4 + CP7 בפאזה 12, וכל **חמש** השאלות (⛔ לא ארבע, ⛔ לא "רובן") |
| **B56** | §06 | "A login-gated dashboard — a real Supabase Auth sign-in screen, not an open page, so the app behaves like the internal tool it's meant to be." | דשבורד מאחורי לוגין | 11 | 4, 10, 10A | 12 | planned | פאזה 11 (CP1): מסך התחברות Supabase Auth אמיתי (`signInWithPassword` דרך הלקוח הרשמי; ⛔ `anon/publishable key` בלבד בדפדפן), ⛔ לא דף פתוח — `authenticated-shell` מוצג רק אחרי `200` מ-`/api/me`, ו-`403` (ארגון שאינו `northbound`) מציג `forbidden-notice` ללא נתונים כלל. ראיה: מקרי הפרכה 6/9ב/12 + `docs/design/states/login-signin-error.jpg`/`bootstrap-403.jpg`; הפריסה החיה אומתה כמגישה את ה-SPA (שער 11→12, 18.09.2026; אומת מחדש 22.09.2026 אחרי 11A — 8/8 הנכסים ש-11A שינתה מוגשים זהים ל-blob שלהם ב-`HEAD`). ⛔ חסר לסגירה: ראיית קבלה חיה — התחברות אמיתית מול Supabase, פאזה 12 |
| **B57** | §06 | "A short write-up (nice to keep as REPORT.md) capturing your findings and the business recommendations from the work packages" | `REPORT.md` עם ממצאים והמלצות | 13 | 5, 6, 10A | 12 | planned | אינו קיים (אומת) |
| **B58** | §06 | "A quick demo — an optional 3–5 minute screen-recording of the deployed app in action." | הקלטת דמו | — | — | — | N/A | אופציונלי בבריף; נדחה ביודעין ב-SPEC |
| **B59** | §06 | "A stranger can open your live URL, sign in, get a prediction for a new customer, see the follow-up and budget insights, and read your recommendations — without you touching anything. Your repo tells them how it was built and how to run it themselves." | רף הסיום מקצה לקצה | 12 | 9, 10, 11, 13, 10A | 12 | planned | 10A/CP5 נעל הזנה עצמאית שאינה תלויה ב־prefill, אישורי הקשר ותוצאות עם פעולה/מגבלה גלויות. עדיין נדרשים מסע דפדפן בפאזה 12 ו־README בפאזה 13; API חי ומוקאפ אינם סוגרים את הרף. ⚠ **חודד 22.09.2026 (`P12-D10`):** רכיב המסע נסגר רק על ידי **בוחן חיצוני** — אדם שאינו בונה המוצר, ממחשב/פרופיל דפדפן אחר ונקי, בלי עזרת המפתח בזמן הבדיקה — ועל ידי **כל שבע רגלי הנוסח**: URL · התחברות עצמאית · טופס נקי ⛔ בלי prefill/דוגמה · הזנה ידנית של לקוח חדש וקבלת חיזוי עבורו · צפייה ב-Follow-up וב-Budget · קריאה בפועל של בלוקי ההמלצה · אפס התערבות (תואם `SPEC.md:1764`/`:381`); ⛔ dry-run של המשתמש אינו תחליף, ובלעדיו CP7 ופאזה 12 נשארים פתוחים. ⛔ גם מסע מוצלח של בוחן חיצוני אינו מעביר את השורה ל-`done` בפאזה 12 — הרף כולל *"Your repo tells them how it was built"*, כלומר `README.md` בפאזה 13 |

## §07 עקרונות

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B60** | §07 | "Reproducibility. Anyone (including future-you) should be able to clone the repo, follow the README, and stand it up. Pin your dependencies." | שחזוריות + הצמדה | 13 | 1 | 12 | planned | `requirements.txt` מוצמד; README חסר |
| **B61** | §07 | "Secrets stay secret. Everything sensitive goes in environment variables and is excluded by .gitignore — never commit an API key or .env." | secrets ב-env ומוחרגים | 1 | 2, 4 | 12 | done | `.gitignore` · `.env.example` שמות בלבד · **`PHASE4.md:371`** — `.env` מוחרג ואינו tracked · **`PHASE4.md:372`** — סריקת `sb_secret_`/`eyJhbGciOi` על עץ העבודה, כל היסטוריית הגיט בכל הענפים, וגוף+תגובות PR #14; אפס ערכים אמיתיים |
| **B62** | §07 | "Anon key in the browser, service key on the server. The login screen uses Supabase's public anon key; the service-role key never leaves your backend." | הפרדת המפתחות | 4 | 9 | 12 | done | `app/static/app.js:46-50` — `config.supabase_publishable_key` → `createClient`; `app/auth.py:31` — `SUPABASE_PUBLISHABLE_KEY` בלבד; `tests/test_config.py`. ⚠ ה-publishable key מחליף את ה-anon key בנוסח החדש; ה-secret key אינו נדרש ב-runtime ונשאר ב-`scripts/*.py` |
| **B63** | §07 | "No leakage without justification. If you include a feature that looks like an outcome, write down why it's legitimately available at prediction time." | הצדקה כתובה לכל פיצ'ר תוצאה-לכאורה | 8A | 5, 6, 10A | 12 | done | `SPEC.md` § נקודות חיזוי + `docs/feature_matrix.md` §§ נקודות חיזוי/חוזה משמעות וזמן — P4S מוגבל לרוכש ידוע לאחר סגירת חלון גיוס חודשי והשלמת מעקב 1; ארבעת הערכים זמינים לפי תנאי ההפעלה. נכתב במפורש שאין תאריכים שמוכיחים סדר זמן, ולכן ההצדקה היא חוזה שימוש גלוי ולא טענת תיקוף אמפירי |
| **B64** | §07 | "Render or Fly.io are drop-in substitutes for this pillar if you prefer." | היתר לחלופת פריסה | 2 | — | 12 | done | **ההיתר להכרעת Render** |
| **B65** | §07 | "Credit what you borrow. Note snippets from docs or tutorials in comments or the README." | קרדיט למקורות שאולים | 13 | 4, 11 | 12 | planned | ⚠ SRI מוכיח שלמות קובץ, ⛔ לא קרדיט. פאזה 11 מטמיעה עותק מוצמד של `supabase-js` (`e2e/vendor/`) עם מקור/גרסה/`license`/notice מתועדים — ראיה, ⛔ לא סגירה |
| **B66** | §07 | "Use AI tools if you like — but understand what you ship. The point is to be able to explain every line, because that's what makes it yours." | יכולת להסביר את המימוש שנשלח; נימוקים מתועדים להכרעות לא-טריוויאליות ולתלויות חיצוניות | 13 | כולן | 12 | planned | יומני ההכרעות `D#` בכל `PHASEn.md` · `docs/planning/codex-review.md` · ביקורת קוד בכל checkpoint. פאזה 11 הוסיפה 15 הכרעות מתועדות (`P11-D1`–`D15`) ו-13 checkpoints שלכל אחד ראיית ביקורת ב-`ROADMAP.html`; ⚠ קודקס לא היה זמין ברובם, והתחליף היה סבבי ביקורת עצמית מתועדים על כל ממצא (כולל ממצאים אמיתיים ב-CP9/CP10/CP11/CP12/CP13) — התיעוד נשמר כדי שסבב ביקורת חיצוני עתידי ידע מאיפה להתחיל. הסגירה: סעיף ב-`README.md` בפאזה 13 |

---

## B47 — הוסר

חבילה 5 בבריף (§05.5) אינה נושאת שורת "expose the X in your app" נפרדת כמו חבילות
2/3/4/6 — היא מסתפקת ב-B44 (ויזואליזציה) ו-B45 (המלצה בדשבורד). מזהה `B47` שוריין
בסבב תכנון קודם עבור שורת expose שלא קיימת בפועל, ותוקן. **פאזה 9 היא contributor**
ל-B44 ול-B45 (המימוש שמאפשר את שתיהן), ⛔ אין דרישת בריף עצמאית לשחזר.

## סיכום כמותי

**74 דרישות אטומיות** (B1–B66 עם פיצולים, בניכוי B47 שהוסר): `done` 41 · `planned` 16 · `gap` 15 · `N/A` 1 · `parent` 1.
