# פאזה 2 — פריסה ל-Render (FunnelIQ)

> **תיעוד האישור.** פאזה 2 בוצעה בשלושה שערים, כל אחד באישור מפורש נפרד:
> שער 1 (הכנת `render.yaml`/`.python-version` ומיזוג PR #3) · שער 2 (חיבור
> ה-repository ל-Render, יצירת Blueprint, deploy ראשון) · שער 3 (בדיקת
> auto-redeploy, בתיעוד למטה). כל מיזוג ל-`main` אושר בנפרד לפני ביצועו.
>
> **מה האישור כיסה:** פריסת שלד ה-FastAPI הקיים עם `/health` בלבד, לפני
> Supabase, Auth, מודלים או endpoints עסקיים — כדרישת פאזה 2.
>
> **מה האישור לא כיסה:** restart יזום ומדידת התאוששות, ובדיקה ממכשיר/רשת
> אחרת ללא תלות במחשב המקומי — אלה ממתינים לאישור נפרד וייכללו בהמשך מסמך זה.

---

## א. שער 1 — תצורת הפריסה

| פריט | ערך |
|---|---|
| Branch | `feat/deploy`, נוצר מ-`main` מסונכרן |
| `.python-version` | תוכן מדויק `3.12.14`, commit `acbbaae` |
| `render.yaml` | commit `de51113` |
| בדיקות מקומיות | `pytest`: 1 passed, בסביבת `pro1_FunnelIQ` · תחביר YAML תקין · `git diff --check` נקי · סריקת סודות/tokens/נתיבים אישיים — נקייה |
| PR | [#3](https://github.com/drorsh88AI/funneliq-marketing-intelligence/pull/3) |
| CI | push run ו-pull_request run — שתיהן `success` |
| מיזוג | rebase, ללא tags, SHA-ים חדשים לאחר מיזוג: `7d57d77` (Python pin), `808df39` (render.yaml) |

**`render.yaml` שנפרס בפועל:**

```yaml
services:
  - type: web
    name: funneliq
    runtime: python
    plan: free
    region: frankfurt
    branch: main
    autoDeployTrigger: commit
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    healthCheckPath: /health
```

---

## ב. שער 2 — חיבור Render, Blueprint ו-deploy ראשון

| פריט | ערך |
|---|---|
| חיבור GitHub | דרך GitHub App של Render, **מוגבל ל-`funneliq-marketing-intelligence` בלבד** (תוקן לאחר הענקת גישה רחבה מדי בטעות בשלב ראשון) |
| Blueprint | נוצר מ-`main`, זוהה אוטומטית מ-`render.yaml` |
| שירות | `funneliq` — runtime Python · plan **free** · region **frankfurt** |
| כרטיס אשראי / תשלום | **לא נדרש** בשום שלב |
| Deploy 1 | סטטוס **Live**, אין שגיאות ב-Logs |
| URL ציבורי | `https://funneliq.onrender.com` |
| `GET /health` — בדיקה 1 | `200 OK`, `{"status":"ok"}` · `Date: Mon, 31 Aug 2026 19:38:52 GMT` · `rndr-id: 86677f28-ee86-4fde` · `CF-RAY: a33e7f7f3d7c5591-TLV` |
| `GET /health` — בדיקה 2 (כ-3 דק' לאחר מכן) | `200 OK`, `{"status":"ok"}` · `Date: Mon, 31 Aug 2026 19:41:29 GMT` · `rndr-id: 05e0e518-9c0f-45d0` · `CF-RAY: a33e8351aaf1d31d-TLV` |
| ROADMAP | `docs: mark phase 2 gate 2 checkpoints verified`, PR [#6](https://github.com/drorsh88AI/funneliq-marketing-intelligence/pull/6), CI ירוק בשתי ריצות, מוזג rebase כ-`96bff62` |

**מגבלות המסלול (`free`), מאומתות מול תיעוד Render הרשמי:**

- 0.1 CPU / 512MB RAM.
- Spin-down אחרי 15 דקות חוסר פעילות; cold start ~דקה בבקשה שמעירה את השירות.
- 750 שעות instance חינמיות לחודש לכל workspace.
- אין SSH, אין דיסק מתמיד, אין scaling. לא מיועד לייצור אמיתי לפי הצהרת Render עצמה.

---

## ג. שער 3 — בדיקת auto-redeploy

| פריט | ערך |
|---|---|
| הטריגר | מיזוג PR [#7](https://github.com/drorsh88AI/funneliq-marketing-intelligence/pull/7) ל-`main` (rebase), merge commit `9d7a975` — `docs: record phase 2 gate 1-2 evidence` |
| SHA שנפרס | `9d7a975b9a9d59397ae2cd635c8c8ae6cf5a3d3b`, מאומת ידנית בדשבורד Render מול deploy חדש שנוצר **אוטומטית** (`autoDeployTrigger: commit`, בלי פעולה ידנית ב-Render) |
| סטטוס ה-deploy | **Live** — אומת ידנית בדשבורד |
| `GET /health` לאחר האימות | `200 OK`, `{"status":"ok"}` · `Date: Mon, 31 Aug 2026 19:53:29 GMT` · `rndr-id: ef193bef-b33f-4c7c` · `CF-RAY: a33e94e90e537d3c-TLV` |

**מסקנה:** push ל-`main` (דרך מיזוג PR) מפעיל redeploy אוטומטי ב-Render ללא כל
פעולה ידנית בצד השירות — דרישת סעיף 04 בבריף מאומתת.

---

## ד. שער 4 — restart יזום והתאוששות

| פריט | ערך |
|---|---|
| הפעלה | **Restart service** בדשבורד Render (לא deploy חדש, לא ניקוי build cache) — בוצע ידנית על ידי המשתמש |
| זמן הלחיצה (UTC) | `2026-08-31T20:01:16Z` |
| בדיקת `/health` ראשונה לאחר הלחיצה | `2026-08-31T20:01:23Z` → **200 OK**, `{"status":"ok"}` — **7 שניות** אחרי הלחיצה |
| בדיקות המשך (יציבות) | `20:01:49Z` · `20:02:04Z` · `20:02:19Z` · `20:02:35Z` — כולן `200 OK`, `{"status":"ok"}` |
| סטטוס בדשבורד | חזר ל-**Live** מיד לאחר הלחיצה — אומת ידנית על ידי המשתמש, במקביל לבדיקות `/health` |

**זמן ההתאוששות שנמדד בפועל: כ-7 שניות** מהלחיצה ועד לתשובת `200` ראשונה,
ויציבות מאומתת על פני כדקה נוספת. **אין ערך רשמי מתועד ב-Render ל-restart
של instance רץ** — הסף הרשמי היחיד שתועד (health-check timeout 5 שניות,
ביטול deploy אחרי 15 דקות) אינו סף restart. הזמן הנמדד כאן קצר משמעותית מ-
~דקה ה-cold start המתועד להתעוררות ממצב spin-down — כצפוי, כיוון שזה restart
של שירות **רץ**, לא הפעלה מחדש אחרי spin-down.

**מסקנה:** השירות מתאושש מ-restart יזום ומחזיר `/health` תקין ללא תלות
במחשב המקומי — דרישת סעיף 04 בבריף מאומתת.

---

## ה. שער 5 — בדיקה ממכשיר/רשת חיצוניים

| פריט | ערך |
|---|---|
| בדיקה | ידנית, על ידי המשתמש, ממכשיר נייד ברשת סלולרית — לא רשת ה-Wi-Fi/מחשב המקומי |
| URL | `https://funneliq.onrender.com/health` |
| תוצאה שדווחה | נגיש, מחזיר `{"status":"ok"}` |
| בדיקה מקבילה מהצד שלי | `2026-08-31T20:09:35Z` → `200 OK`, `{"status":"ok"}` — לתיעוד תואם-זמן |

**מסקנה:** השירות נגיש באופן ציבורי אמיתי, ללא תלות ברשת או במכשיר המקומי
של המפתח — דרישת סעיף 06 בבריף ("stranger can open your live URL") מאומתת
עבור `/health`; שאר מסע הקבלה (login, תחזיות, תובנות) ממתין לפאזות 3–12.

---

## ו. סיכום קבלה — פאזה 2

| קריטריון קבלה (SPEC/ROADMAP) | סטטוס | ראיה |
|---|---|---|
| `/health` מחזיר 200 ב-URL הציבורי | ✅ | סעיפים ב', ד', ה' — מספר בדיקות עצמאיות |
| push ל-GitHub מפעיל redeploy | ✅ | סעיף ג' — commit `9d7a975` |
| `/health` חוזר זמין אחרי restart יזום | ✅ | סעיף ד' — התאוששות ~7 שניות |
| נגישות ממכשיר/רשת חיצוניים | ✅ | סעיף ה' |
| CI ירוק על ה-commit האחרון ב-`main` | ✅ | `b807c7c`, run success |
| אין secrets/Supabase/Auth/מודלים בפאזה 2 | ✅ | נסרק בכל commit — סעיפים א'–ד' |
| אין כרטיס אשראי/תשלום בשום שלב | ✅ | מתועד בסעיף ב' |

**כל 16 משימות פאזה 2 ב-`ROADMAP.html` מסומנות `done` עם ראיה.** התוכן עומד
בקריטריוני הקבלה שנקבעו מראש.

---

## ז. אישור סגירה סופי

| פריט | ערך |
|---|---|
| אישור | מפורש, בהודעת המשתמש: *"אני מאשר סופית את סגירת פאזה 2"* |
| זמן (UTC) | `2026-08-31T20:13:58Z` |
| היקף האישור | סגירת פאזה 2 בלבד — **אינו** אישור לתכנון או ביצוע פאזה 3 |
| `execution_status` בפאזה 2 | `done` (16/16 תתי-משימות, 100%) |

**פאזה 2 הושלמה.** ממתין לאישור מיזוג PR #10 בלבד. פאזה 3 נשארת
`execution_status: not_started`, `planning_status: outline_only` — ללא שינוי.
