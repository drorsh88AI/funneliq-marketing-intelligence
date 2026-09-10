# פאזה 9 — מימוש API

> **סטטוס:** אושרה לביצוע 09.09.2026 (טיוטה 8, אחרי שבעה סבבי ביקורת Codex).
> checkpoints 1–10 בוצעו ואומתו על ענף `feat/api`; checkpoint 11 (push →
> PR → CI → מיזוג → auto-deploy → ראיה חיה → סגירה) ממתין לאישור נפרד לכל
> שלב, לפי מדיניות השער האחידה.
>
> מסמך זה הוא **הגרסה הקנונית** של התכנון שאושר. תכנון D1–D12 המקורי (מ-
> 08.09.2026, לפני הרחבת 8A) נשמר מחוץ לגיט ואינו מקור עוד — כל הפניה
> אליו מוחלפת בהכרעות המעודכנות כאן.

## מקורות האמת

| מקור | תפקיד |
|---|---|
| `FunnelIQ_Assignment.html` | הדרישה |
| `docs/planning/REQUIREMENTS.md` | מרשם 73 הדרישות האטומיות |
| `docs/planning/SPEC.md` | התכן (תוקן ב-D20 לפני האישור הסופי) |
| `docs/planning/PHASE8A.md` | ההרחבה לנתיב השביעי (P4S) |
| `docs/api/openapi.json` + `app/schemas.py` | החוזה הנעול, ⛔ לא נפתח בפאזה זו |

---

## 0. תיקונים מצטברים לאורך סבבי הביקורת

שבעה סבבי ביקורת Codex, כל אחד עם ממצא שנבדק בהרצה ולא התקבל כלשונו:

| סבב | שגיאה שנתפסה | תיקון |
|---|---|---|
| 1 | תכנון D1–D12 קודם קיים מחוץ לגיט — לא "לא נכתב מעולם" | הבסיס הוא התכנון הקודם, לא תכנון מאפס |
| 1 | "ה-API אינו יכול לייבא `scripts.train`" | הוא כבר מייבא אותו, ב-P4/P4S בלבד (`_add_budget_tier`) |
| 1 | שלושת ה-exception handlers נעדרו | D7 |
| 1 | קריטריון אחד לחמשת הכללים בארבעת נתיבי ה-POST | פוצל: `FunnelInput`=5, `EarlyFunnelInput`=3 |
| 2 | חוזה הפריקה הורחב בטעות ל-`_Winsorizer` | אינו באף ארטיפקט פרוס (רק `_add_budget_tier`) |
| 2 | הקבלה בדקה צורה בלבד, לא נכונות | נוספה קבוצת parity סמנטי |
| 3 | ספירת קריטריונים לא עקבית עם הכותרת | ספירה נעולה פר-קבוצה |
| 4 | "ספירת GET מושכת 3,163 ערכים" — שגוי | `max_rows=1000` ב-Supabase; `.range(0,0)` מחזיר שורה אחת |
| 4 | D19 (retries/timeout) נדחה לפאזה 12 | נעול בפאזה 9 |
| 5 | רשימת קודי HTTP קשיחה (`503/520/504`) | הוחלפה בכלל "כל 5xx ⇒ 503" |
| 6 | `SPEC.md` לא עודכן לפאזה 8A — פספסתי בביקורת עצמאית | D20, תיקון חוסם |
| 6 | ראיה חיה תוכננה רק לשני נתיבי insights | נוספה ק' 75 — שבעת הנתיבים |
| 7 | הסיווג `"42501".isdigit()==True` היה עלול לנתב ל-500 במקום 403 | D16: הענף נבחר לפי `type(code) is int` בלבד |
| 7 | `column_status()` היה מסווג עמודות P4S שגוי (D21) — סווג בטעות כ"חוב תיעוד" ולא כבאג | תוקן ל-D21 מלא: באג קוד + חוב תיעוד |

---

## 1. מצב מאומת בהרצה (לפני הביצוע)

25 עובדות נבדקו בפועל, לא הונחו. המרכזיות:

| # | ממצא |
|---|---|
| 2 | P4/P4S **בלבד** גוררים `scripts.train` בטעינה (39→197 / 39→196 MB); P2/P3/P6 לא |
| 8 | חריגה לא-מטופלת **ו**-`ResponseValidationError` היו מחזירות `500 text/plain`, לא `ErrorDetail` JSON |
| 11 | שני ה-views (`budget_tier_insight`, `followup_insight`) בלי `ORDER BY` |
| 16 | fixture דטרמיניסטי, ⛔ ללא CSV: P2 `28.5647529271`/`23.4254696970`/`33.7040361572` · P3 `0.8060147259` · P4 `0.8131065511` · P4S `0.4053842048` |
| 19 | `max_rows=1000` ב-`supabase/config.toml:18` |
| 22 | `APIError.code` הוא `int` כשגוף השגיאה אינו JSON, ו-`str` כשהוא PostgREST |
| 25 | `"42501"` (SQLSTATE) הוא `str` ש-`.isdigit()==True` — המלכודת שהצדיקה את D16 |

(הרשימה המלאה בת 25 הפריטים תועדה בטיוטה המאושרת ובקוד המבחנים
המתאימים תחת `tests/`.)

---

## 2. ההכרעות (D1–D21)

### D1 — routers, שונה ב-8A
`app/predict.py`: `ltv` · `upsell` · `referral` · `super-customer` ·
`simulate/budget`. `app/insights.py`: `followup` · `budget-tiers`.

### D2 — טעינה דו-שלבית
בעלייה: שבעה נכסי JSON (`metrics.json`, חמשת ה-`*.meta.json`,
`P6_simulation.json`) — קיום, parsing, סכמה. SHA-256 על חמשת ה-`joblib`
בלבד (בהאשינג בלבד, ⛔ ללא `joblib.load`), מול `meta.checksums`. כשל ⇒
fail-fast, ⛔ לא 500. בבקשה הראשונה: loader single-flight נעול לכל
משימה; פריקה או אי-תאימות ספרייה שנכשלו ⇒ 500.

### D3 — צימוד ה-pickle
⛔ אין בנייה מחדש של ארטיפקטים · ⛔ אין shim ל-`sys.modules` · ⛔ אין
ייבואים עצלים ב-`scripts/train.py`. `app/` ⛔ אינו מייבא `scripts.train`
ברמת המודול. ההיקף המדויק: **`scripts.train._add_budget_tier` בלבד**
(⛔ לא `_Winsorizer` — אינו קיים באף ארטיפקט פרוס).

### D4 — לקוח Supabase פר-בקשה
```python
options = ClientOptions(
    headers={"Authorization": f"Bearer {token}"},
    auto_refresh_token=False,
    persist_session=False,
    postgrest_client_timeout=10,      # D19
)
```
תלות `yield`; ב-`finally` פעם אחת, בהצלחה ובכשל: `client.auth.close()` ·
`client.postgrest.aclose()`. ⛔ לעולם לא `postgrest.auth()` על lru_cache
משותף · ⛔ לעולם לא secret key.

### D5 — `access_token()` כתלות בסיס
`current_user` בנוי מעליה. `/api/me` נשאר שלושה שדות; הטוקן לעולם לא
מוחזר בגוף התשובה.

### D6 — `HTTPBearer`
`HTTPBearer(scheme_name="BearerAuth", auto_error=False)`. שתי דלתאות
מוצהרות: `/api/me` מאבד `422`; ה-scheme הופך case-insensitive
(`bearer`/`BEARER` מתקבלים).

### D7 — שלושה exception handlers
`RequestValidationError`→422 `{loc,msg,type}` (בלי `input`/`ctx`) ·
`ResponseValidationError`→500 `ErrorDetail` · `Exception` (catch-all)→500
`ErrorDetail`. ⛔ בלי traceback, שם חריגה, נתיב קובץ או ערכי קלט בגוף.

### D8 — projection מנורמל
שבעת הנתיבים העסקיים, סגור הפניות הסכמות, ו-`securitySchemes` —
deep-equal מול `docs/api/openapi.json`. מוחרגים: `info`, `/health`,
`/api/config`, `/api/me`, ה-mount הסטטי.

### D9 — OOD לפני `predict`
תגובת OOD ⛔ אינה טוענת את ה-`joblib` כלל.

### D10 — sigmoid ו-`budget_tier` כבר ב-joblib
⛔ ה-API אינו מפעיל אותם מחדש. ⛔ אין החלת `p6_log1p_smearing`
(תיעוד מחקרי, לא הוראת הגשה).

### D11 — `simulate/budget` = lookup טהור
⛔ `P6.joblib` אינו נטען בשום מסלול בקשה.

### D12 — קריאות Supabase, סדר וקדימות
`.order()` מפורש בכל קריאה (שני ה-views בלי `ORDER BY`). עימוד מותאם +
ספירה עצמאית (D19). שלמות חמשת שלבי ה-`followup` נבדקת **לפני** בניית
מודל התגובה.

### D13 — `conformal_interval` ל-`app/inference.py`
שינוי מול ההכרעה הקודמת ("אין שינוי ב-`train.py`"): הועברו
`conformal_interval` ו-`_require_finite_scalar`, עם ייבוא חוזר ב-
`scripts/train.py`. ⛔ נגיעה בשם שב-pickle (`_add_budget_tier`) ·
⛔ בנייה מחדש · ⛔ שינוי ייבואים אחרים ב-`train.py`. חובת הוכחה: חמשת
ה-SHA ללא שינוי, 448 בדיקות בסיס ללא שינוי, `import app.inference` נטול
תופעות לוואי.

### D14 — `evidence_level_from_n` ציבורי
נקרא **דרך המודול** (`schemas.evidence_level_from_n(...)`), ⛔ לא כשם
מיובא ומוצמד — כדי ש-spy יתפוס גם את הרכבת `simulate/budget` וגם את
ה-validator של `StrategyResult`.

### D15 — `assess()` מקבל את מחלקת האזהרה כפרמטר
`OODWarning` ל-P2/P3/P4, `SuperCustomerOODWarning` ל-P4S — תת-מחלקה,
⛔ לעולם לא מאוחדת לאותו discriminated union (`PHASE8A.md` D19).

### D16 — שגיאות Supabase, סיווג לפי משמעות
`APIError.code` הוא `int` כשגוף השגיאה אינו JSON, ו-`str` כשהוא
PostgREST/Postgres. **סדר הסיווג נעול:** קודם `type(code) is int` ⇒
ענף א; אחרת ⇒ ענף ב, ורק בתוכו `strip().upper()`. ⛔ אין להמיר מחרוזת
ל-`int`, ⛔ אין `isdigit()` כמבחין — `"42501"` (SQLSTATE) הוא `str`
ש-`.isdigit()==True`, ומבחן מבוסס-ספרות היה מחזיר 500 במקום 403.

**ענף א (`int`):** `401`→401 · `403`→403 · `408`/`429`/כל `5xx`→503 ·
כל היתר→500.
**ענף ב (`str`, אחרי נרמול):** `PGRST301/302/303`→401 · `42501`→403 ·
`08*`/`53*`/`PGRST000/001/002/003`→503 · `PGRST205` (view חסר)→**500**
(drift בפריסה, ⛔ לא תקלת זמינות) · כל היתר→500.
מחוץ ל-`APIError`: `httpx.TransportError`→503.

**קדימות נעולה בכל נתיב:** `401 > 403 > unavailable/503 > 200`. שגיאת
הרשאה ⛔ אינה נבלעת ל-`unavailable`; הרשאה בחלק אחד + זמינות בשני ⇒ קוד
ההרשאה; `401`+`403`⇒`401`; ⛔ אין נתונים בגוף לצד קוד הרשאה, גם אם חלק
אחר כבר הצליח.

### D17 — אימות ארטיפקטים
| מה | מתי | כישלון |
|---|---|---|
| קיום/parsing/סכמה, שבעת נכסי ה-JSON | בעלייה | fail-fast |
| SHA-256 חמשת ה-`joblib` מול `meta.checksums` | בעלייה | fail-fast |
| `algo` במפתחות `metrics[task]`; `ood_bounds` מכסה `feature_columns` | בעלייה | fail-fast |
| `feature_columns == MODEL_INPUT_FEATURES[task]` בסדר | בעלייה | fail-fast |
| `feature_dtypes` — בדיוק קבוצת הפיצ'רים, ערכים נתמכים | בעלייה | fail-fast |
| ה-`DataFrame` הנבנה: עמודות/סדר/dtypes מדויקים | בכל בקשה | 500 |
| `classes_ == [0,1]` (P3/P4/P4S) | בטעינה העצלה | 500 |
| `predict_proba(...)[:, 1]`, ⛔ לא `[:, -1]` | בכל בקשה | — |

### D18 — שפת ה-`message` באזהרות
אנגלית מכנית. העברית למשתמש מורכבת בפאזה 11 מהשדות המובנים.

### D19 — retries ו-timeout, נעול בפאזה 9
`.retry(False)` על **כל** שאילתות המשתמש (⛔ ואין שכבת retry משלנו) ·
`postgrest_client_timeout=10` (פאזה 12 מודדת ומכווננת) · ספירה עצמאית:
`.select("source_row_id", count="exact").eq("purchased", 1).order("source_row_id").range(0,0)`,
משתמשים רק ב-`response.count`. ⛔ אין `head=True` (באג ספרייה: `HEAD`
אינו מנוסה שוב כמו `GET`).

### D20 — תיקון `SPEC.md`, חוסם, קודם לאישור
`SPEC.md` לא היה מעודכן לפאזה 8A: `P4S` הופיע אפס פעמים, מפת הפאזות
דילגה 8→9, ומטריצת חמש שאלות המייסדת מיפתה את שאלה 3 ל-`P4`/`referral`
עם פאנל "0–100". תוקן ב-13 מקומות (ר' commit היישום): שאלה 3 ⇒
`super-customer`/P4S; `P4` נשאר endpoint משלים לחיזוי הפניה; נוספה שורת
P4S בהצגת אי-הוודאות, בטבלת המדדים, בתקציב ההתאמות, במפת הפאזות
(שורת 8A), ובכל מקום שמנה שישה נתיבים. ⛔ אין שינוי ב-`docs/api/openapi.json`,
ב-`app/schemas.py` או ב-`models/` — תיקון תיעוד בלבד.

### D21 — באג ב-`column_status()` + חוב תיעוד מפאזה 8A
`column_status(c, "P4S")` סיווג שגוי 10 עמודות כ-`"Feature"` (מחוץ ל-
`FEATURES["P4S"]`), כי הכלל הישן ("19 פחות יעד והחרגות") תקף לארבע
המשימות המקוריות בלבד. תוקן בענף חמישי: עמודה שאינה ב-`FEATURES[task]`
⇒ `Excluded`. **no-op מוכח** לארבע המשימות המקוריות (רגרסיה ייעודית);
P4S: 4 `Feature` / 15 `Excluded` / 0 `Derived`. `docs/feature_matrix.md`
עודכן בהתאם — נגזר מהפונקציה, ⛔ לא עוקף אותה. בוצע **בתחילת checkpoint
1**, על ענף `feat/api`, ⛔ לעולם לא על `main`.

---

## 3. מיפוי לבריף

**נסגרו** (`owner=9`): `B8` · `B12` · `B28` · `B36` · `B52` — ✅ **ראיה חיה
בוצעה** (ק' 72–73, 75, 2026-09-10, מול Render אחרי מיזוג `b176eab`),
⛔ לא על סמך `TestClient`/mocks בלבד. `status: done` ב-`REQUIREMENTS.md`.
**contributors:** `B41` · `B44` · `B45` · `B50` · `B55b` · `B56` · `B59` ·
`B62` · `B10`.
**סטיות מאושרות, לא נפתחות מחדש:** Render (`B64`) · בלי notebook.

`B41` (ציון 0–100) נשארת `planned` — ה-API מחזיר הסתברות 0–1; ה-IA
מתעדכן בפאזה 10, התצוגה בפאזה 11.

---

## 4. Checkpoints — סטטוס וראיה

⚠ **precondition נעול לכל checkpoint, מעכשיו ואילך:** לפני תחילת checkpoint
`N`, checkpoint `N-1` חייב להיות מסומן `done` **עם commit/ראיה רשומים
בטבלה** — לא מספיק שבוצע "בזיכרון" בלי שורה כאן. checkpoint 0 (יצירת
הענף + שלב 0) הוא ה-precondition המפורש של checkpoint 1: אין קוד API
לפני שלושת קבצי התיעוד מחויבים בגיט.

| # | תוכן | סטטוס | ראיה |
|---|---|---|---|
| 0 | `main` נקי → יצירת `feat/api` → שלב 0 (PHASE9.md חדש, SPEC.md D20, ROADMAP.html, REQUIREMENTS.md) | ✅ done ⚠ **בוצע שלא לפי הסדר** — ראו הערה למטה | `93c4faa`, `5dad544` |
| 1 | D21 (`column_status`) + D13 (`app/inference.py`) | ✅ done | `82eda3c`, `4b391f2`; 448→453 |
| 2 | `HTTPBearer` + `access_token` (D5/D6) | ✅ done | `6622b84`; 453→460 |
| 3 | `app/artifacts.py` — loader + D17 | ✅ done; ולידציית meta הושלמה בשלושה סבבי ביקורת: (1) `alpha`/`conformal_quantile`/`base_rate`/`calibration_status`/`calibration_method` כמפתחות קיימים; (2) המבנה הפנימי של `metrics[task][algo]`, כל בלוק `*_holdout`, `P6_strategy_ranking.ranked`, `P6_simulation[sid].levels`, ו-`ood_bounds[col].min/max`; (3) **חוזה הערכים עצמו** — finite (דוחה NaN/±inf), טווחי `Field(ge=.../le=...)` הזהים ל-`app/schemas.py`, וערכי Literal נעולים (`interval_method`, `calibration_method`, `calibration_status` פר-משימה) | `9977589`; 460→526 · `9b91d0c`; →716 · `e6659eb`; →743 · `a072f74`; →771 |
| 4 | routers + שלושת ה-handlers (D7) | ✅ done | `262b694`; 526→533 |
| 5 | `ltv`/`upsell`/`referral` | ✅ done | `46c62fe`; 533→582 |
| 6 | `super-customer` | ✅ done | `7eac95e`; 582→594 |
| 7 | `app/supabase_client.py` — לקוח, D16, D19 | ✅ done; `status_for_supabase_error` תוקן ל-`type(code) is int` (במקום `isinstance`), ביקורת קוד לפני checkpoint 11 | `e8fc0a0`; 594→632 · `9b91d0c` |
| 8 | `simulate/budget` + `budget-tiers` | ✅ done; **ק' 72 בוצעה** (ראיה חיה, 2026-09-10); `.order("tier_order", nullsfirst=False)` מפורש נוסף בביקורת קוד, והבדיקה חוזקה מ-substring לערך המדויק `tier_order.asc.nullslast` | `b2a38a9`; 632→653 · `9b91d0c` · `e6659eb` |
| 9 | `followup` — עימוד + קדימות | ✅ done; **ק' 73 בוצעה** (ראיה חיה, 2026-09-10); `.order("stage_order")` מפורש נוסף בביקורת קוד, והבדיקה חוזקה לערך המדויק `stage_order.asc` | `8361a05`; 653→669 · `9b91d0c` · `e6659eb` |
| 10 | HTTP מלא + projection | ✅ done | `168100e`; 669→695 |
| 11 | סגירה: ביקורת ✅ → סריקת סודות מקומית ✅ → push ✅ → PR ✅ → CI ✅ → מיזוג ✅ → auto-deploy ✅ (מאומת, ר' הערה) → ראיה חיה (ק' 72–73, 75) ✅ → אימות `main` ✅ → סגירה ⏳ (אישור נפרד) | 🔄 בביצוע | merge commit `b176eab`; אימות `main` בוצע על `5beac02` (תצלום, ר' הערה) |

⚠ **checkpoint 0 בוצע שלא לפי הסדר, בפועל, לא רק לפי התיעוד:** `main` נקי
ויצירת `feat/api` בוצעו נכון לפני D21 — אך שלב 0 עצמו (`93c4faa`,
`5dad544`) נכתב **אחרי** checkpoint 10 (`168100e`), לא לפניו כפי שהתכנון
המאושר דרש. עשרה checkpoints של קוד רצו בלי `PHASE9.md` קנוני קיים
בגיט, בלי תיקון D20 ב-`SPEC.md`, ובלי `ROADMAP.html`/`REQUIREMENTS.md`
מסונכרנים — התיקון הרטרואקטיבי סוגר את פער התיעוד, **אינו** הופך את
סדר הביצוע המקורי לתקין, והוא שנחשף רק כשהמשתמש בדק את המצב, לא
כתוצאה מבדיקה עצמית שהופעלה כאן.

⚠ **`9b91d0c` עצמו דיווח על סגירת ארבעה ממצאים, ושניים מהם לא היו סגורים
בפועל** — טעות דיווח שנייה מאותו סוג בדיוק כמו checkpoint 0 למעלה (הצגת
תיקון כשלם לפני שהוא). המשתמש בדק שוב ומצא: (א) ולידציית `artifacts.py`
כיסתה רק את השדות **ב-meta.json עצמו**, לא את המבנה הפנימי של
`metrics.json`/`P6_simulation.json`/`ood_bounds` שה-routes קוראים מהם
בפועל; (ב) `app/schemas.py` תוקן ל"חמש response families" — **שגוי, יש
שש**, טעות חדשה שאני הכנסתי באותו commit; (ג) בדיקות ה-`order` בדקו
substring בלבד, לא את הכיוון/NULL-position בפועל. שלושתם נסגרו ב-`e6659eb`,
עם 27 בדיקות פרמטריות חדשות מול `models/` האמיתי. **הלקח החוזר: "תוקן"
דורש ראיה שנבדקה ברמת המבנה הפנימי הנצרך בפועל, לא רק שקיים commit
ו-pytest ירוק.**

⚠ **סבב ביקורת שלישי (`a072f74`):** המשתמש מצא ש-`e6659eb` בדק presence
וטיפוס בלבד, לא **חוזה הערכים**: `mean_roc_auc=2`, `P6.lower > upper`,
`calibration_status="anything"`, NaN/inf בגבולות OOD — כולם היו עוברים
startup ונכשלים רק בזמן בקשה. תוקן: `_is_number` דוחה NaN/±inf (נקודת
מינוף יחידה שמשדרגת את כל הבדיקות הקיימות); טווחי `metrics[task][algo]`
ו-`*_holdout` זהים ל-`Field(ge=.../le=...)` ב-`app/schemas.py`; ערכי
Literal נעולים (`interval_method`, `calibration_method`,
`calibration_status` פר-משימה, כולל ש-P4S ⛔ אינו מקבל `"uncalibrated"`
בעוד P3/P4 כן); `ranked` נבדק כרשימת מחרוזות **לפני** `set()`; P6
`point/lower/upper` finite ו-`lower<=upper`.
⚠ **כמעט-תקלה שנתפסה עצמאית תוך כדי:** הניסיון הראשון לתקן את ה-docstring
של `ClassificationMetrics` (בקשה מפורשת של המשתמש) **שבר את
`test_group1_reexport_matches_locked_artifact`** — docstring של מחלקת
Pydantic נפלט מילולית ל-`description` ב-`docs/api/openapi.json`, **החוזה
הנעול** שאסור לשנות בשום שלב. `pytest -q` המלא תפס את זה מיד; התיקון
הוחזר, וההבהרה על P4S עברה להערת מקור מעל המחלקה במקום לתוך ה-docstring
עצמו — משיג את אותה מטרה בלי לגעת בחוזה הנעול.

**771/771 בדיקות ירוקות** (מבסיס 448; 695 עד סוף checkpoint 10; +21
מ-`9b91d0c`; +27 מ-`e6659eb`; +28 מ-`a072f74`). כל commit רץ מול
`pytest -q` מלא לפני ואחרי. חמשת הארטיפקטים ללא שינוי לאורך כל הביצוע
(SHA-256 נבדק בקריטריון 31); `models/` **וגם `docs/api/openapi.json`**
לא נגעו בהם בשלושת תיקוני ביקורת הקוד. `main` לא נגע בו — כל ה-commits
על `feat/api` בלבד.

⚠ **CI על PR #24 נכשל בריצה ראשונה, בשני ה-jobs זהה** —
`tests/test_artifacts.py::test_import_app_inference_has_no_file_io_side_effect`
(קריטריון 45): `import app.inference` בתת-תהליך נקי על CI (Ubuntu,
Python 3.12.14) ביצע קריאת `open()` **אחת**, בעוד מקומית (Windows,
771/771 כולל הבדיקה הזו) — אפס. נשלל: אי-התאמת גרסאות (`requirements.txt`
נעול לזהה למותקן מקומית), `load_dotenv()` ב-`scripts/load_data.py`
(נקרא בתוך פונקציה בלבד, לא ברמת מודול), ושחזור מקומי עם `HOME`/
`XDG_CACHE_HOME` טריים (עדיין אפס). **תוקן ב-`c5b1ebe`**: `import pandas`
הועבר לתוך `build_input_frame`, ו-`from app.artifacts import
get_artifact` הועבר לתוך `predict_if_in_domain` — `app.inference`
כעת ללא ייבוא חיצוני כלשהו ברמת המודול (רק `math`), כך שסיבת ה-`open()`
המדויקת (כנראה תופעת לוואי חד-פעמית של pandas/numpy על Linux טרי) הופכת
לבלתי-רלוונטית: היא כבר לא יכולה לקרות מ-`import app.inference` בלבד.
שלוש בדיקות ב-`tests/test_inference.py` שעשו monkeypatch על
`app.inference.get_artifact` עודכנו לתקוף את `app.artifacts.get_artifact`
(שם ה-import המקומי אכן פותר את השם). בדיקת קריטריון 45 עצמה שומרת על
**אותו תנאי הצלחה בדיוק** (`calls == {'open': 0, 'json.load': 0}`) אך
כעת אוספת stack מצומצם לכל קריאה, שיוצג בהודעת הכשל אם זה יישנה —
בלי צורך ב-commit אבחוני נפרד. `771/771` מקומית; `models/` ו-
`docs/api/openapi.json` לא נגעו בהם. נדחף לאותו PR #24 (`d69d56c`).

✅ **שתי ריצות ה-CI החוזרות עברו בהצלחה** —
[run 34417611846](https://github.com/drorsh88AI/funneliq-marketing-intelligence/actions/runs/34417611846)
ו-[run 34417614089](https://github.com/drorsh88AI/funneliq-marketing-intelligence/actions/runs/34417614089),
שניהם `pass`. אומת עצמאית פעמיים — פעם אחת על ידי המשתמש ופעם על ידי
`gh pr checks 24`/`gh pr view 24` — ש-PR #24 עומד על `MERGEABLE`/`CLEAN`
מול `head d69d56c`. **מיזוג אושר בנפרד ובוצע** (`gh pr merge 24 --merge`): merge commit
`b176eab` על `main`. CI על `main` אחרי המיזוג — `success` (run `34418532666`).

✅ **auto-deploy אומת (read-only, ללא deploy ידני):** `GET /health` מול
`https://funneliq.onrender.com` → `200 {"status":"ok"}`; `GET /openapi.json`
הציבורי (ללא אימות) מציג `title="FunnelIQ API"`, `version="0.4.0"`, ו-10
נתיבים כולל כל שבעת נתיבי העסק — טביעת-אצבע חד-משמעית ש-`main` שממוזג
פרוס בפועל (נתיבים אלה לא היו קיימים לפני המיזוג, ואין commit מתחרה
אחריו). ⚠ **הסתייגות שהמשתמש ביקש לתעד במפורש:** זו הוכחה **לגרסת הקוד
שרצה** (מסקנה עקיפה, לוגית), ⛔ **לא** קריאה ישירה מרשומת deploy של
Render בעצמה (אין גישת API/dashboard לזה בסביבה הזו) — אין לתאר זאת
כהוכחה חד-משמעית לקישור ל-SHA המדויק.

✅ **ק' 72/73/75 (ראיה חיה) בוצעו** — 2026-09-10, מול `https://funneliq.onrender.com`
אחרי המיזוג ל-`b176eab`, עם `demo-northbound`/`demo-noorg` אמיתיים
(המשתמש הריץ סקריפט מקומי בעצמו; קלוד מעולם לא ראה את הסיסמאות).
**ק' 72** (`budget-tiers`): `demo-northbound`→200 (`rows=3`) · טוקן לא
תקין→401 · `demo-noorg`→403. **ק' 73** (`followup`): `demo-northbound`→200
(`stages=5`, `population_n=3163`) · אותם שני מסלולי שלילה (401/403).
**ק' 75** (שבעת הנתיבים): כולם 200 עם `demo-northbound`; `/health` נשאר
200 בסוף הרצף. ⚠ **הראיה נמדדה ברמת status code בלבד** — לא נבדק בצד
הלקוח שגוף התגובה תואם את `app.schemas` שדה-שדה. **אך זו לא הסתייגות
ריקה:** כל שבעת הנתיבים מוגדרים עם `response_model=` (D7/D8), ו-FastAPI
עצמו מריץ ולידציה מלאה מול אותו מודל Pydantic לפני שהתגובה נשלחת —
כשל שם נתפס על ידי `ResponseValidationError` וממופה ל-**500** (לא 200,
ר' `app/main.py`). **200 הוא אפוא ראיה של ממש שהתגובה עברה את ולידציית
הסכמה של השרת עצמו**, לא רק "הנתיב לא קרס". ⛔ אין
token/password/Authorization מתועדים בשום מקום.

✅ **אימות `main` בוצע על `5beac02`** — תצלום נכון לרגע האימות, **לפני**
תיקוני התיעוד הנוכחיים (שיוצרים commit חדש ולכן head חדש): `main`
המקומי מזוהה בדיוק עם `origin/main`, עץ עבודה נקי, `pytest -q` מלא
**771/771**, וה-CI על `main` ירוק (run `34421247013`). ⚠ **חיפוש בתכנון המאושר (הן ב-
`PHASE9.md` והן בטיוטה שאושרה) לא העלה הגדרה נוספת, מפורשת ומראש, למה
"אימות main" אמור לכלול מעבר לארבעת אלה** — אין קריטריון נפרד שדורש
בדיקה נוספת. משום כך אין הרצה חוזרת של דבר: ארבעת אלה **הם** אימות
`main`, לא תת-קבוצה שלו.

---

## 5. קריטריוני קבלה — 78, ספירה נעולה A8·B8·C13·D20·E14·F2·G13

> ⛔ אין יעד מספרי לכמות הקריטריונים; ⛔ אין להסיר כיסוי שכבר חשף כשל.
> קריטריונים אטומיים — לא להשוות ל"קבוצות בדיקה" של פאזות קודמות
> (`PHASE8.md` סופר 19 קבוצות = 118 בדיקות בפועל; יחידות שונות).

### A · חוזה, סכמה, מקורות אמת (1–5, 76–78)
1. `pytest -q` ירוק; אף בדיקה קיימת לא שונתה כדי לעבור.
2. שבעת הנתיבים מוגשים מ-`app.main.app`, מחזירים 200 תואם-סכמה.
3. `projection` מנורמל deep-equal ל-`docs/api/openapi.json`.
4. `securitySchemes.BearerAuth` נפלט מהאפליקציה החיה.
5. שלושת ה-`GET` אינם נושאים `422`.
76. `docs/feature_matrix.md` עמודת P4S זהה ל-`column_status()` המתוקנת; אין שורת `Target`.
77. רגרסיה: D21 הוא no-op לארבע המשימות המקוריות.
78. אינווריאנטי P4S (4/15/0) בקבוצה נפרדת, לא כלל "19 פחות".

### B · הרשאות (6–13)
6–7. 401/403 בכל נתיב עסקי. 8–9. חמשת/שלושת כללי הקלט. 10. גוף 422
`loc/msg/type` בלבד. 11. `/api/me` בלי 422. 12. bearer case-insensitive.
13. `/api/me` בדיוק שלושה שדות.

### C · שגיאות, קדימות, retries (14–26)
14–17. גוף 500/503 = `ErrorDetail` JSON, בלי דליפת מידע פנימי.
18–19. סיווג `str`/`int` פרמטרי מלא, כולל regression נגד `isdigit()`.
20–22. 503/520/TransportError = קריאה יחידה. 23–25. קדימות וה-negative
control. 26. אחד/שני חלקי `followup` נכשלים.

### D · נכסים, טעינה, בידוד (27–45, 74)
27–36. כל שבעת הנכסים, כל שדה נדרש, fail-fast. 37–43. `classes_`,
כשל/retry בטעינה, טעינה מקבילית, בידוד `scripts.train` (תת-תהליכים).
44–45. OOD לא טוען joblib; `app.inference` נטול תופעות לוואי. 74.
ה-`DataFrame` בפועל תואם `feature_columns`/`feature_dtypes` בדיוק.

### E · parity סמנטי (46–59)
46. precondition fixture. 47–50. P2 מדויק מול הפייפליין, כולל חיתוך
באפס. 51. גבולות OOD פר-פיצ'ר. 52–54. unobserved/OOD/מרובה. 55. מחלקת
האזהרה הנכונה. 56–58. `model_version`/מדדים/`evidence_level_from_n`
משותף. 59. הודעות ASCII.

### F · P6 (60–61)
60. כל שדה תואם ל-`P6_simulation.json`. 61. parity קבוע↔ארטיפקט.

### G · Supabase, מחזור חיים, ראיה חיה (62–75)
62–67. הגדרות לקוח, לקוח נפרד, סגירה כפולה, JWT אמיתי, אין secret key.
68–70. ספירה עצמאית, `.retry(False)`, עימוד מלא. 71. `budget-tiers`
ממוין, אפס שורות. **72–73, 75. ראיה חיה — ✅ בוצעו (2026-09-10, checkpoint 11).**

---

## 6. מה הפאזה אינה כוללת

מסכים ו-HTML/CSS/JS · תצוגת 0–100 · מסך ל-`super-customer` · בנייה מחדש
של ארטיפקטים · shim ל-`sys.modules` · ייבואים עצלים ב-`train.py` · שכבת
retry משלנו · השתקת `DeprecationWarning` גלובלית · `httpx.Client` ידני ·
view/מיגרציה חדשים · אימון/כיול/Bootstrap מחדש · פתיחת Holdout ·
`CORSMiddleware` · rate limiting · cache · `README`/`REPORT` · שינוי
`openapi.json` · שינוי `FEATURES`.

---

## 7. סיכונים ובלמים — 37 רשומים

הרשימה המלאה (R1–R37) מתועדת בטיוטה שאושרה; כל אחד מוצמד להכרעה
ולקריטריון שסוגר אותו. הבולטים שנפתרו בפועל בביצוע: R8א (מלכודת
`isdigit`, D16 + ק' 18) · R22 (סדר/dtype שגוי ב-`DataFrame`, D17 + ק' 74)
· R28 (ארטיפקט משתנה בשקט, ק' 31 עם ליטרלים מעץ `93612c1`) · R32/R35
(B8/B12/B28/B36/B52 "נסגרות" על mocks בלבד — נסגר ב-2026-09-10 עם ראיה
חיה בפועל מול Render, ר' סעיף 3 וסעיף 4 למעלה).

---

## 8. מה נותר לפני סגירת הפאזה

1. **checkpoint 11**: ביקורת קוד ✅ (שלושה סבבים) → סריקת סודות מקומית ✅
   → push ✅ → PR #24 ✅ → CI ✅ ירוק → מיזוג ✅ (`b176eab`) → auto-deploy
   ✅ מאומת (`/health`=200, `/openapi.json` חי) → ק' 72/73/75 ✅ (ראיה
   חיה, 2026-09-10) → אימות `main` ✅ → **נותר**: סגירת הפאזה בלבד
   (אישור נפרד).
2. ✅ `docs/planning/REQUIREMENTS.md` עודכן: `B8`/`B12`/`B28`/`B36`/`B52`
   → `status: done`, עם ראיה מפורטת (status codes, timestamp, תוויות
   מושחרות) לכל אחד.
3. ✅ `ROADMAP.html`: `planning_status → approved_for_execution`,
   `execution_status → in_progress` הוגדרו; ראיה per-checkpoint מעודכנת
   דרך checkpoint 11.
