# פאזה 8 — נעילת חוזה API

תכנון מפורט. תוצר הפאזה: **חוזה נעול** — סכמות Pydantic וארטיפקט OpenAPI
שפאזה 9 ממלאת.

⛔ **אין כאן מימוש.** אין טעינת מודלים, אין קריאות Supabase, אין חיזוי, אין
אימון, אין רישום routes באפליקציה החיה. פאזה 8 קובעת **צורה**, לא התנהגות.

---

## א. מטרת הפאזה

`SPEC.md § חוזי תגובה` נועל את **שמות** 14 שדות החוזה ואת שני ערכי
`interval_method`. `docs/IA.md` (תוצר פאזה 7) נועל **מה כל מסך נדרש להציג**.

מה שנשאר פתוח, ומה שפאזה זו סוגרת: **הצורה** — אילו סכמות, איזה קינון,
אילו טיפוסים, מה nullable ומה לא, אילו קודי סטטוס, ומה מוחזר כשערך אינו
רלוונטי או אינו ניתן לחישוב.

⚠ אין בפאזה זו שאלת מוצר פתוחה. כל 13 ההכרעות הן הכרעות סכמה.

---

## ב. מצב מאומת — נבדק בהרצה, לא הונח

| # | נבדק | תוצאה |
|---|---|---|
| 1 | `feature_columns` בארבעת ה-`meta.json` | P2/P3/P4 = **13, זהים ובאותו סדר**; P6 = **14** (כולל `purchased`) |
| 2 | `app.features.FEATURES` מול `meta.json` | `FEATURES["P2"]`=14 (כולל `leads_not_answered`), `FEATURES["P6"]`=15 — **אינם שווים ל-13** |
| 3 | `scripts/train.py:171-176` | `model_feature_columns(task)` **כבר קיים** = `FEATURES[task]` פחות `leads_not_answered`; שורה 2517 כותבת ממנו את `meta.json.feature_columns` |
| 4 | `scripts/train.py:1485` | `STRATEGY_ALLOCATIONS` **כבר קיים**: `{"2x20000_1x10000":[(20000,2),(10000,1)], "10x5000":[(5000,10)], "25x2000":[(2000,25)], "100x500":[(500,100)]}` |
| 5 | `scripts/train.py:39` | כבר מייבא מ-`app.features` — כיוון התלות תומך בהעברה |
| 6 | `base_rate` | P3 = `0.4635` · P4 = `0.4271` · ⛔ אין ב-P2 ואין ב-P6 |
| 7 | `calibration_status` / `calibration_method` | `calibrated` / `sigmoid` — ב-P3 וב-P4 בלבד |
| 8 | `P2.meta.json.alpha` | `0.05` ⇒ `nominal_coverage = 0.95` |
| 9 | `metrics.json → P2_holdout.conformal_coverage` | `0.9289` — הכיסוי הנמדד, נפרד מהנומינלי |
| 10 | `P6.meta.json.bootstrap_percentiles` | `[2.5, 97.5]` — **גלובלי**, לא פר-אסטרטגיה |
| 11 | `models/P6_simulation.json` | `levels:{"20000":{"n":57},"10000":{"n":161}}` · `n_bootstrap_used=1000` **פר-אסטרטגיה** · ⛔ **אין בו `count`** |
| 12 | `metrics.json → P6_strategy_ranking` | `{ranked:[100x500, 25x2000, 10x5000, 2x20000_1x10000], top_two_overlap:true, verdict:"…"}` — **שמור, לא מחושב** |
| 13 | `meta.json.algo` כמפתח חיפוש | `catboost`/`xgboost`/`logistic`/`linear` — **זהה לשם הבלוק** ב-`metrics.json[task]` |
| 14 | מפתחות ה-CV הנדרשים, לכל ארבע המשימות | `mean_mae`/`mean_rmse`/`mean_r2` ב-P2 וב-P6 · `mean_roc_auc`/`mean_pr_auc`/`mean_brier`/`mean_log_loss` ב-P3 וב-P4 — כולם קיימים תחת האלגוריתם הזוכה |
| 15 | `app/auth.py:49` | `authorization: str \| None = Header(default=None)` — **פרמטר header, לא security scheme** |
| 16 | `app/auth.py` (הגדרה חסרה) | מחזיר **500** כשהגדרת Supabase חסרה |
| 17 | `20260901164904_views.sql` — `followup_insight` | חמש שורות · `stage_order` 1–5 · `stage` = `followup_1..followup_5` · `drop_rate` דרך `nullif` · `having count(*) > 0` |
| 18 | `20260901164904_views.sql` — `budget_tier_insight` | `CASE` **בלי `ELSE`** ⇒ פער `1501–1999` מייצר שורה עם `tier_order=null` ו-`budget_tier=null` וערכי `n_records`/`conversion_rate` אמיתיים |
| 19 | גבולות `propensity_band` | `IA.md:199-201` + `PHASE7.md:57-59` — `0.9×`/`1.1× base_rate`, סגורים, בלי רווח וללא חפיפה |
| 20 | חמשת כללי הוולידציה | `IA.md:103-107` |
| 21 | `POST /api/simulate/budget` — grep מלא | שלושה מופעים חיים: `IA.md:19`, `IA.md:493`, `SPEC.md:289`. `ROADMAP.html` מזכיר את הנתיב (495, 898) **בלי מתודה**. מופע רביעי ב-`codex-history.md:129` — **ארכיון חתום** |

---

## ג. הכרעות התכנון — D1–D13

### D1 — הפקת OpenAPI מאפליקציית חוזה מבודדת

`app/schemas.py` מחזיק את כל מודלי הבקשה והתגובה.
`scripts/export_openapi.py` בונה מופע `FastAPI()` **חד-פעמי בתוך הסקריפט**,
רושם עליו את ששת הנתיבים העסקיים כדי שהסכמות ייכנסו ל-`components.schemas`,
ומייצא ל-`docs/api/openapi.json`.

⛔ **אין רישום ב-`app/main.py`. אין routes חיים. אין stubs שמחזירים 501.**
הנימוק המכריע: Render פורס אוטומטית מ-`main`, ולכן route שמחזיר 501 היה
עולה לשירות החי.

**למה בכלל צריך לרשום נתיבים:** FastAPI מכניס ל-`components.schemas` רק
סכמות ש-route מפנה אליהן. בלי רישום — הקובץ יוצא ריק ואין מה לנעול.

**בדיקת drift בפאזה 8:** ייצוא חוזר חייב להיות זהה ל-`docs/api/openapi.json`.

**בדיקת drift בפאזה 9:** ⚠ אין להשוות את כל `app.main.app.openapi()` לקובץ
שמכיל שישה נתיבים בלבד — האפליקציה החיה נושאת גם `/health`, `/api/config`
ו-`/api/me`. ההשוואה היא על **projection מנורמל**: ששת הנתיבים העסקיים,
הסכמות הנגישות מהם בסגור ההפניות, והגדרות האבטחה.

### D2 — `evidence_level`

| משימה | ערכים | חובה? |
|---|---|---|
| P2 · P3 · P4 | `"low"` \| `null` | nullable |
| P6 | `"high"` \| `"medium"` \| `"low"` | **חובה** |

`null` פירושו **שאין גירעון תמיכה מתועד** — ⛔ אינו טענה לראיות גבוהות.
`"low"` ב-P2/P3/P4 מופעל אך ורק כאשר `ad_budget` נמצא בטווח 500–20,000 אך
אינו אחד מ-16 הערכים הנצפים (`IA.md:254`).

⛔ **אין `high` ב-P2/P3/P4** — אין `n` לרשומה בודדת בשום ארטיפקט.
`"low"` נשאר ערך חוקי ב-P6 אף שאף אסטרטגיה אינה מקבלת אותו בפועל; הכלל
מגדיר שלוש רמות, ו⛔ אין להזיז ספים כדי שרמה תתמלא.

⚠ **הספים של P6 (`n≥200` / `50≤n<200` / `n<50`) הם החלטת פאזה 7 ואינם שדה
שמור בשום ארטיפקט.** אסטרטגיה רב-רמתית מקבלת את **המינימום**.

**תיאום מול `PHASE7.md:100`** — שם נכתב שהתוויות *"מחושבות offline… לא בזמן
בקשה"*. ההבהרה: **`n` והספים נקבעו offline** ואינם משתנים; `P6_simulation.json`
שומר **`n` בלבד ולא את התווית**. פאזה 9 גוזרת ממנו את התווית **גזירה
דטרמיניסטית** בטעינת הארטיפקט או בהרכבת התגובה. ⛔ אין בכך חישוב תחזיות או
טווחים מחדש, ולכן אין סתירה — אבל הניסוח ב-`PHASE7.md` אינו מדויק כפי
שנכתב, **ומעודכן בשני המסמכים**.

### D3 — `warnings` כ-discriminated union

⛔ לא מערך מחרוזות, ⛔ ולא מודל יחיד עם שדות אופציונליים ו-validator —
מודל כזה אינו מבטא ב-OpenAPI אילו שדות נדרשים לכל `code`.

`Field(discriminator="code")` ⇒ `oneOf` + `discriminator` ב-OpenAPI.

| מודל | `code` | שדות | מקור |
|---|---|---|---|
| `OODWarning` | `"ood_feature_out_of_range"` | `code, message, feature, value, min, max` | `meta.json.ood_bounds` |
| `UnobservedBudgetWarning` | `"unobserved_budget_level"` | `code, message, feature="ad_budget", value` | `meta.json.observed_ad_budget_values` |

הנימוק: `IA.md` §9.2 דורש את **הסיבה הקונקרטית** — איזה שדה, מחוץ לאיזה
גבול. מחרוזת בלבד אינה חושפת הקשר מובנה ומצמידה את הלקוח לניסוח; union
מובחן מאפשר הצגה, לוקליזציה ובדיקות דרך **שדות יציבים** ולא דרך טקסט.

### D4 — חמש משפחות תגובה, לא מודל-על

`LtvPrediction` · `PropensityPrediction` · `BudgetSimulation` ·
`FollowupResponse` · `BudgetTiersResponse`.

⛔ **אין מודל אחד עם 14 שדות nullable** — הוא מוחק את ההבחנה בין "לא רלוונטי
למשימה" לבין "לא הוחזר", בדיוק ההבחנה שמטריצת `IA.md` §8 בנתה.
**שדה שאינו רלוונטי למשימה אינו מופיע בסכמה שלה כלל.**

### D5 — התנהגות OOD

**OOD הוא קלט חוקי ⇒ HTTP 200.** ⛔ אינו 422; קלט פגום ומרחק מהתפלגות
האימון הם שני דברים (`IA.md` §3.2).

| סכמה | מתאפס ל-`null` |
|---|---|
| `LtvPrediction` | `point_estimate` · `lower_bound` · `upper_bound` |
| `PropensityPrediction` | `event_probability` · `propensity_band` |

בשני המקרים: `in_training_domain=false`, ו-`warnings` מכיל לפחות
`OODWarning` אחד.

⛔ **אינם מתאפסים — פר-משפחה**, כי שדה שאינו בסכמה אינו "לא-מתאפס" אלא
פשוט אינו קיים (D4):

| סכמה | שדות שנשארים כפי שהם |
|---|---|
| `LtvPrediction` | `interval_method` · `interval_details` · `model_version` · `model_algorithm` · `metrics` |
| `PropensityPrediction` | `base_rate` · `calibration_status` · `calibration_method` · `model_version` · `model_algorithm` · `metrics` |

אלה **מאפייני המודל, לא תוצאת החיזוי**.

**`evidence_level` אורתוגונלי ל-OOD (D2/D5).** הוא נגזר אך ורק ממבחן
ה-`ad_budget` הנצפה ושומר על ערכו העצמאי גם כאשר `in_training_domain=false`.
רשומה שהיא OOD בפיצ'ר אחד **וגם** נושאת תקציב פנימי לא-נצפה מחזירה
`evidence_level="low"` ו**שתי אזהרות** — `OODWarning` ו-`UnobservedBudgetWarning`.
הנימוק: `IA.md` §9.2 קובע שפאנל OOD מציג את הסיבה הקונקרטית, לא תווית
רמת-ראיות; השתיים אינן מתחרות.

**ערך `ad_budget` פנימי שלא נצפה (למשל 3,500):** ⛔ **אינו OOD** — חיזוי
מלא, `in_training_domain=true`, `evidence_level="low"`,
`UnobservedBudgetWarning` (`IA.md:443`).

### D6 — בלוק מדדים: הזוכה בלבד, ורק מה שהמסך דורש

`model_algorithm` נקרא מ-`meta.json.algo`. אותה מחרוזת משמשת גם כמפתח
לאיתור בלוק הזוכה בתוך `metrics.json[task]` (אומת בסעיף ב, ממצא 13) — אין אי-בהירות
לפאזה 9 איזה בלוק לקרוא.

| מודל | `cv` | `holdout` |
|---|---|---|
| `RegressionMetrics` (P2 · P6) | `mean_mae` · `mean_rmse` · `mean_r2` | `mae` · `rmse` · `r2` |
| `ClassificationMetrics` (P3 · P4) | `mean_roc_auc` · `mean_pr_auc` · `mean_brier` · `mean_log_loss` | `roc_auc` · `pr_auc` · `brier` · `log_loss` |

⛔ **אין `accuracy` ואין `n_holdout`** — `IA.md` §3.4 ו-§6 אינם דורשים אותם,
והכלל הוא "רק מה שהמסך דורש". תוספת עתידית = שינוי חוזה שעובר בשער.

⛔ **אין endpoint ייעודי למדדים או לגרסאות** — נדחה בפאזה 7 כשטח API קישוטי.

⚠ **מגבלת הכיול של P3 אינה שדה בחוזה.** אין לה שדה שמור (`P3_calibration`
מכיל `calibration_method`/`calibration_status`/`winner` בלבד). היא **טקסט UI
סטטי**, מיוחס לנתוני `metrics.json → P3_holdout.calibration_curve` ולהכרעת
פאזה 7 (`PHASE7.md:68-70` · `IA.md:161` · `codex-review.md:360`, שורת D1
בלבד — ⛔ **לא** שורת D2, שאינה מזכירה כיול).
⛔ **לא `PHASE6.md`** — הניסוח אינו מופיע שם.
`IA.md` §3.4 יסמן אילו פריטי `<details>` מגיעים מ-API ואילו סטטיים.

### D7 — כיסוי P2: `interval_details`, תת-מודל של `LtvPrediction` בלבד

| שדה | מקור | ערך |
|---|---|---|
| `nominal_coverage` | `1 − P2.meta.json.alpha` | `0.95` |
| `measured_coverage` | `metrics.json → P2_holdout.conformal_coverage` | `0.9289` |

⛔ **לא בתוך `RegressionMetrics`** — הוא משותף ל-P6, שאין לו כיסוי נמדד;
הכנסתם לשם הייתה יוצרת בדיוק את ה-nullable המלאכותי ש-D4/D5 מונעים.
השדות נשמרים ב**תת-מודל ייעודי ל-P2**. ⚠ `SPEC § חוזי תגובה` נועל את
**שמות** 14 שדות המינימום — ⛔ **לא את רמת הקינון**; `nominal_coverage`
ו-`measured_coverage` אינם מ-14 ולכן מיקומם הוא הכרעת פאזה 8.

### D8 — מבנה P6

`bootstrap_iterations` ו-`bootstrap_percentiles` יושבים ב**שתי רמות שונות**,
כל אחד ברמה שבה הוא שמור בפועל:

| שדה | רמה | מקור |
|---|---|---|
| `bootstrap_percentiles` | `BudgetSimulation` | `P6.meta.json` (גלובלי) |
| `bootstrap_iterations` | `StrategyResult` | `P6_simulation.json[strategy].n_bootstrap_used` |
| `model_algorithm` | `BudgetSimulation` בלבד | כל האסטרטגיות משתמשות באותו מודל |

`allocations: [{ad_budget, count, sample_size}]` — ⛔ **אין `sample_size`
סקלרי ברמת האסטרטגיה**. `2x20000_1x10000` נשענת על `n=57` וגם על `n=161`;
`sample_size` יחיד היה מוחק את אחד מהם. `evidence_level` נגזר מהמינימום
בלי לשכפל את המספר כשדה נוסף.

⚠ **`count` אינו קיים ב-`P6_simulation.json`** — מקורו `STRATEGY_ALLOCATIONS`
בלבד. ⛔ **אין לפרסר את `strategy_id`** כדי להסיק אותו.

### D9 — דירוג וחפיפה נקראים, לא מחושבים

`top_two_overlap` ⇐ `metrics.json → P6_strategy_ranking.top_two_overlap`.
`rank` ⇐ סדר `P6_strategy_ranking.ranked`.

⛔ **אין חישוב מחדש** — הערך כבר נעול ב-`metrics.json`, וחישוב כפול יוצר
**שני מקורות אמת** שעלולים לסטות מהתוצר הקפוא של פאזה 6.
⚠ **אין זו הפרת S9.** S9 היא חריגת פרוטוקול ספציפית סביב פתיחת ה-**Holdout**
(`PHASE6.md:765`, D22), וחישוב מהטווחים השמורים אינו נוגע ב-Holdout. הנימוק
כאן הוא מקור אמת יחיד, לא S9.

⛔ **`verdict` אינו נכנס לחוזה** — מחרוזת עברית מנוסחת, הערת אנליסט;
`IA.md` §6 כבר קובע את מבנה הודעת החפיפה. הטקסט הוא שכבת תצוגה.

### D10 — `GET /api/simulate/budget`

⛔ לא `POST`. אין גוף בקשה כלל: ארבע האסטרטגיות וסכום ה-₪50,000 קבועים,
והתוצאה היא lookup לתוצר offline (`models/P6_simulation.json`).

**פאזה 8 מחליפה במפורש את המתודה** ב-`GET`, משום שאין לנתיב גוף בקשה.
⚠ זו הכרעת חוזה חדשה, ⛔ **לא תיקון "שארית מיושנת"**: `POST` נכתב במתכוון
בטבלת חמש השאלות ב-`SPEC.md:289` ונישא משם ל-`IA.md`. אומת ש-`PHASE7.md`
**אינו מכיל הכרעת מתודה כלל** — המתודה מעולם לא נדונה, רק הועתקה. לפי
דפוס S11 ההחלפה מוצהרת ומעודכנת במקור, ולא נמחקת בשקט.

**היקף העדכון — אומת ב-grep מלא:** `docs/IA.md:19` · `docs/IA.md:493` ·
`docs/planning/SPEC.md:289`. `ROADMAP.html` מזכיר את הנתיב **בלי מתודה** —
אין מה לשנות בו. ⛔ `docs/planning/codex-history.md:129` הוא **ארכיון חתום**
ואין לגעת בו; עריכת ארכיון היא שכתוב היסטוריה.

⛔ `app/main.py` אינו משתנה בפאזה 8.

### D11 — קודי סטטוס

| קוד | מצב |
|---|---|
| **200** | הצלחה · OOD · אפס שורות ב-`budget-tiers` · כשל חלקי ב-`followup` |
| **401** | אין token, לא תקין או פג תוקף |
| **403** | מאומת בלי `organization=northbound` |
| **422** | טיפוס שגוי או הפרת אחד מחמשת כללי `FunnelInput` — ⛔ **שלושת נתיבי ה-`POST` בלבד** (ד.0) |
| **500** | תקלה פנימית או הגדרת Supabase חסרה (התנהגות קיימת, `app/auth.py`) |
| **503** | אין שום חלק שמיש בתשובה, או שירות תלוי אינו זמין |

**שתי סכמות שגיאה נפרדות:**
`ErrorDetail = {"detail": str}` ל-401/403/500/503 ·
`HTTPValidationError = {"detail":[{"loc":[…], "msg":str, "type":str}]}` ל-422.
⚠ `{"detail": str}` לבדו **אינו** מתאר את מבנה 422 של FastAPI.

⚠ **`budget-tiers` עם אפס שורות = 200 + מערך ריק.** השרת הצליח; הפרשנות
כשגיאת זמינות היא כלל תצוגה (`IA.md` §2.2). ⛔ אין להסיק ממנו 401 או 403.

⚠ **401/403 גוברים על כשל חלקי** — כשקוד ההרשאה חוזר, אין להחזיר נתונים
לצדו.

### D12 — כשל חלקי ב-Follow-up

`GET /api/insights/followup` מרכיב **שני חלקים** ממקורות שונים (`IA.md`
§7.1): חמש שורות הנשירה מ-`followup_insight`, וההתפלגות המצטברת בשרת
מ-`funnel_records`. כשל באחד אינו מפיל את השני.

כל חלק הוא **union מפורש**:

```
{"status": "available",   "data":  …}
{"status": "unavailable", "error": {"reason_code": …, "message": …}}
```

⛔ מערך ריק או `null` לבדם אינם מבחינים בין כשל לבין תוכן.

`reason_code`: `data_unavailable` · `aggregation_mismatch`.
אי-סגירות בסכום התדירויות ממפה ל-`aggregation_mismatch` ו⛔ **לעולם לא
להתפלגות חלקית**.

| מצב | קוד |
|---|---|
| שני החלקים תקינים | 200 |
| חלק אחד נכשל | **200** — התקין נשמר, שנפל מסומן `unavailable` |
| שני החלקים נכשלו | **503** |

### D13 — סכמת אבטחה מוצהרת

**הממצא:** `app/auth.py:49` מממש את ההרשאה כ-
`authorization: str | None = Header(default=None)` — פרמטר header רגיל,
**לא security scheme של FastAPI**. לכן ה-OpenAPI של האפליקציה החיה אינו
מכיל `components.securitySchemes` ואינו מכיל בלוק `security`, ולא יכיל
אותם. בלי תיקון, קריטריון הקבלה על הצהרת האבטחה ובדיקת ה-projection של
פאזה 9 אינם ברי-מימוש.

**ההכרעה:** אפליקציית החוזה תשתמש ב-
`HTTPBearer(scheme_name="BearerAuth", auto_error=False)` כתלות אבטחה
**בכל ששת הנתיבים**. `auto_error=False` נבחר כדי לשמר את המצב הקיים שבו
היעדר header מגיע לקוד ומקבל 401 מנוסח, ולא 403 אוטומטי של FastAPI.

**חובת פאזה 9 — מוצהרת כאן, לא נגזרת:** `current_user` ב-`app/auth.py`
יעבור לאותו dependency בדיוק, תוך שמירת התנהגות 401/403 הקיימת ובדיקות
התאמה. ⛔ **השינוי הזה אינו מתבצע בפאזה 8** — `app/auth.py` אינו נגוע.

⚠ החלופה שנשקלה ונדחתה: להצהיר בחוזה את אותו parameter header של היום —
כנה, אך מוותרת על `security` לגמרי ומרוקנת את בדיקת הקבלה מתוכן.

---

## ד. סכמות מדויקות

### ד.0 — ששת הנתיבים העסקיים

| # | מתודה | נתיב | משימה | בקשה | תגובה |
|---|---|---|---|---|---|
| 1 | `POST` | `/api/predict/ltv` | P2 | `FunnelInput` | `LtvPrediction` |
| 2 | `POST` | `/api/predict/upsell` | P3 | `FunnelInput` | `PropensityPrediction` |
| 3 | `POST` | `/api/predict/referral` | P4 | `FunnelInput` | `PropensityPrediction` |
| 4 | `GET` | `/api/simulate/budget` | P6 | ⛔ אין | `BudgetSimulation` |
| 5 | `GET` | `/api/insights/followup` | P5 | ⛔ אין | `FollowupResponse` |
| 6 | `GET` | `/api/insights/budget-tiers` | חבילה 1 | ⛔ אין | `BudgetTiersResponse` |

⚠ **`PropensityPrediction` משרתת שני נתיבים** — P3 (`upsell`, `base_rate`
`0.4635`) ו-P4 (`referral`, `base_rate` `0.4271`). אותה סכמה, שני ארטיפקטים
שונים; ⛔ אין לגזור את המשימה מהסכמה.

**מפת קודי התגובה לפי נתיב:**

| קוד | נתיבים | נימוק |
|---|---|---|
| `200` | כל השישה | — |
| `401` · `403` | כל השישה | `Depends(HTTPBearer(...))` על כולם (D13) |
| `500` · `503` | כל השישה | D11 |
| **`422`** | **שלושת נתיבי `POST` בלבד** | רק להם יש גוף בקשה שאפשר להפר בו ולידציה |

⛔ **אין להצהיר `422` על שלושת נתיבי ה-`GET`.** אומת אמפירית בסביבת
הפרויקט: FastAPI מוסיף `422` לאופרציה **אך ורק כשהיא מצהירה על פרמטרים או
גוף**; `Depends(HTTPBearer(...))` הוא security requirement ו**אינו נספר
כפרמטר**. אפליקציית בדיקה עם `POST` בעל גוף ו-`GET` בלי גוף, שניהם עם אותו
`HTTPBearer`, הפיקה `['200','422']` ל-`POST` ו-`['200']` ל-`GET` — בעוד
`security` ו-`components.securitySchemes.BearerAuth` נפלטו לשניהם.
הצהרת `422` ידנית על ה-`GET` הייתה יוצרת **drift מובטח** מול פאזה 9.

⛔ **אלה כל הנתיבים העסקיים.** `/health`, `/api/config` ו-`/api/me` קיימים
מפאזות 1 ו-4, ⛔ **אינם חלק מהחוזה הזה** ואינם נכללים ב-projection של פאזה 9.

⚠ **תוצאת לוואי של D13 שיש לרשום:** `GET /api/me` **נושא היום `422`**
(אומת: `app.main.app.openapi()` מחזיר לו `['200','422']`), משום ש-`auth.py`
מצהיר `authorization` כפרמטר `Header` ולא כ-security scheme. מעבר ל-
`HTTPBearer` בפאזה 9 **יסיר** ממנו את ה-`422`. אין בכך נזק — `/api/me` אינו
חלק מה-projection — אך זהו שינוי בארטיפקט החי, ו⛔ אין לגלות אותו כהפתעה
בפאזה 9.

### ד.0א — חתימת ה-routes באפליקציית החוזה

`scripts/export_openapi.py` רושם כל נתיב בחתימה **נעולה**. החתימה היא מה
שמייצר את הארטיפקט — ⛔ רישום חסר מייצר OpenAPI שגוי בשקט:

```python
@app.post("/api/predict/ltv",
          response_model=LtvPrediction,
          dependencies=[Depends(bearer)],
          responses=ERROR_RESPONSES)          # 401/403/422/500/503
def predict_ltv(body: FunnelInput): ...       # contract-only

@app.get("/api/simulate/budget",
         response_model=BudgetSimulation,
         dependencies=[Depends(bearer)],
         responses=ERROR_RESPONSES_NO_422)    # 401/403/500/503
def simulate_budget(): ...                    # contract-only
```

| רכיב | POST | GET |
|---|---|---|
| `body: FunnelInput` | **חובה** — הוא שמכניס את סכמת הבקשה ל-`components.schemas` | ⛔ אין |
| `response_model` | הסכמה המדויקת לפי ד.0 | הסכמה המדויקת לפי ד.0 |
| `dependencies` | `Depends(bearer)` | `Depends(bearer)` |
| `responses` | 401/403/**422**/500/503 | 401/403/500/503 |

⚠ **גוף ה-handler הוא `...`** — האפליקציה **אינה מופעלת אף פעם**; היא נבנית,
נחקרת ב-`app.openapi()` ונזרקת. ⛔ **אין צורך ב-501 ואין להחזיר דבר.**
⛔ אין רישום ב-`app/main.py` (D1).

**נבדק בקריטריון 2א:** לכל נתיב — `responses["200"]` הוא `$ref` ישיר לסכמה
הנכונה · ל-`POST` יש `requestBody` עם `required: true` המפנה ל-`FunnelInput` ·
ל-`GET` **אין** `requestBody` ו**אין** `parameters`.

### ד.0ב — מדיניות מודלים

בסיס משותף לכל מודלי החוזה:

```python
class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

StrictInt  = Annotated[int,  Field(strict=True)]
StrictBool = Annotated[bool, Field(strict=True)]

class FunnelInput(ContractModel):              # כולו int ⇒ strict ברמת המודל
    model_config = ConfigDict(strict=True)
```

| כלל | נימוק |
|---|---|
| `extra="forbid"` | ברירת המחדל `ignore` **מקבלת** שדות עודפים בשקט (אומת) |
| `allow_inf_nan=False` | ברירת המחדל **מקבלת** `inf`/`nan` ל-`float` (אומת); שניהם אינם JSON חוקי |
| `strict` לכל שדה `int` | ברירת המחדל מקבלת `"1"`→1, **`True`→1**, `1.0`→1 (אומת) |
| `strict` לכל שדה `bool` | ברירת המחדל מקבלת `1`, `0`, `"true"`, `"yes"`, `"on"`, `1.0` (אומת) |

⛔ **מנגנון ה-`strict` — פר-שדה, לא פר-מודל.** אומת:
`ConfigDict(strict=True)` חל על **כל** שדות המודל — במודל מעורב הוא דחה גם
`f="2.5"` בשדה `float`. לכן:

| מודל | מנגנון |
|---|---|
| `FunnelInput` — 13 שדות `int` בלבד | `ConfigDict(strict=True)` ברמת המודל |
| כל מודל מעורב (`LtvPrediction`, `StrategyResult`, `FunnelStage`, `TierRow`, `CallsBucket`…) | `StrictInt` / `StrictBool` **פר-שדה** |

⚠ **`strict` על שדות `float` — לא נדרש.** בדקתי: `strict` float מקבל
`2.5`, `50000`, `np.float32/64` ו-`np.int64`, ודוחה רק `bool` ומחרוזת — ערכים
שפאזה 9 לעולם אינה מייצרת. `allow_inf_nan=False` יחד עם מגבלות
`ge`/`le` המתועדות הוא הדרישה המכריעה שם.

### ⛔ `Literal` מספרי/בוליאני **אינו** מוגן — לא בברירת מחדל ולא ב-`strict`

אומת בסביבת הפרויקט:

| הצהרה | מקבל בטעות | תחת `strict=True` |
|---|---|---|
| `Literal[True]` | `1` · `1.0` | ⛔ **עדיין מקבל** |
| `Literal[50000]` | `50000.0` | ⛔ **עדיין מקבל** |
| `Literal[1,2,3]` | `True` · `1.0` | ⛔ **עדיין מקבל** |
| `list[float]` | `["2.5","97.5"]` | — |

⚠ **הממצא המכריע: `ConfigDict(strict=True)` אינו פותר את זה.** `strict`
מגן על `int`/`bool`/`float` רגילים, אך `Literal` נבדק **אחרי** ה-coercion
ולכן `1` כבר הפך ל-`True` לפני ההשוואה. ⛔ אין קיצור דרך — נדרש
`field_validator(mode="before")` לכל `Literal` מספרי או בוליאני:

| שדה | הגנה |
|---|---|
| `StrategyResult.in_training_domain` | `before`: ⛔ נדחה אלא אם `type(v) is bool and v is True`. ב-OpenAPI נשמר `const: true` |
| `BudgetSimulation.total_budget` | `before`: ⛔ נדחה אלא אם `type(v) is int and v == 50000` (⛔ `bool` נפסל — הוא תת-מחלקה של `int`) |
| `TierRow.tier_order` | `before`: ⛔ נדחה אלא אם `v is None or type(v) is int` — ורק אז ה-`Literal[1,2,3]` |
| `bootstrap_percentiles` | `tuple[Literal[2.5], Literal[97.5]]` — ר' להלן |

**`bootstrap_percentiles` — `tuple`, ⛔ לא `list[float]`.** אומת שהוא נועל
אורך, סדר וערכים בבת אחת ודוחה `("2.5","97.5")` ואת הסדר ההפוך, ונפלט
ל-OpenAPI כ-
`{"type":"array","minItems":2,"maxItems":2,"prefixItems":[{"const":2.5},{"const":97.5}]}`
— כלומר מערך JSON רגיל.

⚠ ⛔ **ה-`tuple` הזה נשאר lax ולא `strict`.** אומת: `tuple` תחת `strict`
**דוחה `[2.5, 97.5]`** — כלומר דוחה בדיוק את מה ש-JSON שולח. `strict` כאן
היה הופך את השדה לבלתי-שמיש.

**כלל `required` — כל שדה בסכמה הוא `required`.**

⛔ **`| null` מתיר ערך `null`, ⛔ לא השמטת המפתח.** אומת: ב-Pydantic
`x: float | None` **בלי `default`** הוא `required` — השמטתו נדחית, ו-
`x=None` מתקבל. ⛔ **אין `default=None` בשום שדה חוזה**: אחרת תגובת OOD
הייתה יכולה **להשמיט** את `point_estimate` במקום להחזירו `null`, והלקוח לא
היה מבחין בין "אין חיזוי" ל"השדה לא הוחזר" — בדיוק ההבחנה ש-D4 בנה.

### ד.1 — בקשה

**`FunnelInput`** — הגוף של שלושת נתיבי `predict`. יורש מ-`ContractModel`
ומוסיף `ConfigDict(strict=True)` **ברמת המודל**, שכן כל 13 שדותיו `int`
(ד.0ב): **13 שדות `int` `strict`, כולם `required`, כולם `ge=0`, ו-
`extra="forbid"`:**

`ad_budget` · `num_leads` · `leads_answered` · `followup_1` · `followup_2` ·
`followup_3` · `followup_4` · `followup_5` · `not_closed` · `closed` ·
`calls_to_closed` · `calls_to_not_closed` · `customer_acquisition_cost`

⛔ `leads_not_answered` אינו שדה — אינו פיצ'ר קלט של אף מודל.
⛔ `referred` אינו שדה — הוא ה-target של P4.
⛔ `purchased` אינו שדה — קבוע באוכלוסיית האימון של P2/P3/P4.

**חמשת כללי הוולידציה החוצים שדות** (`model_validator`) ⇒ **422**:

1. `num_leads > 0`
2. `leads_answered ≤ num_leads`
3. `leads_answered ≥ followup_1 ≥ followup_2 ≥ followup_3 ≥ followup_4 ≥ followup_5`
4. `closed + not_closed = followup_5`
5. אי-שליליות בכל 13 השדות (נאכף ב-`ge=0`)

⚠ הפרה היא **422 ואינה בדיקת OOD**.

⛔ **`strict` כאן אינו קישוט.** אומת בסביבת הפרויקט: בברירות המחדל של
pydantic 2.13.4, `int` מקבל `"1"`→1, **`True`→1** ו-`1.0`→1, ושדות עודפים
מתקבלים בשקט. בלי `strict` ו-`extra="forbid"`, הבקשה
`{"ad_budget": true, …}` הייתה **עוברת** ומייצרת חיזוי.

⛔ שלושת נתיבי ה-`insights`/`simulate` הם `GET` **בלי גוף בקשה ובלי
פרמטרים**.

### ד.2 — `LtvPrediction` (P2)

| שדה | טיפוס |
|---|---|
| `point_estimate` | `float \| null` |
| `lower_bound` | `float \| null` |
| `upper_bound` | `float \| null` |
| `interval_method` | `Literal["split_conformal"]` |
| `interval_details` | `IntervalDetails` |
| `evidence_level` | `Literal["low"] \| null` |
| `in_training_domain` | `StrictBool` |
| `warnings` | `ContractWarning[]` (ייתכן ריק) |
| `model_version` | `str` |
| `model_algorithm` | `str` |
| `metrics` | `RegressionMetrics` |

`IntervalDetails` = `{nominal_coverage: float, measured_coverage: float}`.

מכסה שדות חוזה **1, 2, 3, 4, 8, 10, 11, 12**.

### ד.3 — `PropensityPrediction` (P3 · P4)

| שדה | טיפוס |
|---|---|
| `event_probability` | `float` 0–1 `\| null` |
| `base_rate` | `float` 0–1 |
| `propensity_band` | `Literal["below_base","near_base","above_base"] \| null` |
| `evidence_level` | `Literal["low"] \| null` |
| `in_training_domain` | `StrictBool` |
| `warnings` | `ContractWarning[]` (ייתכן ריק) |
| `model_version` | `str` |
| `model_algorithm` | `str` |
| `calibration_status` | `Literal["calibrated","uncalibrated"]` |
| `calibration_method` | `Literal["sigmoid"]` |
| `metrics` | `ClassificationMetrics` |

⛔ **שני שדות הכיול הם enums סגורים, לא `str` חופשי.** אומת:
`SPEC.md:463-464` — *"`calibration_status = calibrated` רק אם התאמת ה-sigmoid
הצליחה. אחרת `uncalibrated` + אזהרה"*; `scripts/train.py:1431` ו-`1435`
מחזירים `calibration_method="sigmoid"` **גם במסלול הכישלון**, כי השיטה נעולה
מראש.

⚠ **`uncalibrated` אינו נגיש בארטיפקטים הנוכחיים.** אומת:
`scripts/train.py:2507` זורק `RuntimeError("cannot build a deployable
artifact -- calibration failed")` כאשר `calibration_status != "calibrated"`,
ולכן ארטיפקט שנפרס **לעולם אינו נושא** את הערך הזה; בפועל P3 ו-P4 שניהם
`calibrated`. הערך נשאר ב-`Literal` משום ש-`SPEC.md:463-464` מגדיר אותו
כמצב fallback של החוזה — ⛔ לא משום שהוא מצב אפשרי של הארטיפקט.

⚠ **האזהרה שדורש `SPEC.md:464` אינה נכנסת ל-`warnings[]`.** `warnings[]` הוא
union סגור של **שתי אזהרות תמיכת-קלט** (D3), ואילו כשל כיול הוא **תכונת
מודל**. הלקוח מפיק את ההודעה מ-`calibration_status="uncalibrated"` — ערך
שכבר בחוזה, ו-`SPEC.md:470` מגדיר לו design token ייעודי.
⛔ **אין להמציא `warning code` שלישי**, ו⛔ אין להוסיף שדה. זהו אותו דפוס
של מגבלת הכיול ב-D6: מצב מודל ⇒ תצוגה, לא ⇒ `warnings[]`.

**גבולות `propensity_band`** (`IA.md` §4, מוסכמת תצוגה של פאזה 7):

| ערך | תנאי |
|---|---|
| `below_base` | `p < 0.9 × base_rate` |
| `near_base` | `0.9 × base_rate ≤ p ≤ 1.1 × base_rate` |
| `above_base` | `p > 1.1 × base_rate` |

⛔ ההשוואה תמיד מול `base_rate` המדויק מ-`meta.json` (P3 `0.4635`,
P4 `0.4271`), **לעולם לא מול המספר המעוגל בתצוגה**. `1.1 × 0.4635 =
50.985%`, וערך `0.50987` הוא `above_base` לפי הכלל אך `near_base` בהשוואה
ל-`50.99%` מעוגל. העיגול הוא שכבת תצוגה.

⚠ **46.35% הוא שיעור `upsell=1`; 53.65% הוא דיוק ה-majority baseline.**
`base_rate` נושא את הראשון.

⚠ נבחר השם `PropensityPrediction` ולא `ProbabilityPrediction` — השדה הנעול
ב-SPEC הוא `propensity_band`.

מכסה שדות חוזה **5, 6, 7, 8, 10, 11, 12, 13, 14**.

### ד.4 — `BudgetSimulation` (P6)

| שדה | טיפוס |
|---|---|
| `total_budget` | `Literal[50000]` + `before`-validator (ד.0ב) |
| `interval_method` | `Literal["bootstrap_percentile"]` |
| `bootstrap_percentiles` | `tuple[Literal[2.5], Literal[97.5]]` — נועל אורך, סדר וערכים בהצהרה (ד.0ב) |
| `top_two_overlap` | `StrictBool` |
| `strategies` | `StrategyResult[]` `min_length=4, max_length=4`, מסודר לפי `rank` |
| `model_version` | `str` |
| `model_algorithm` | `str` |
| `metrics` | `RegressionMetrics` |

`total_budget` נשאר בחוזה כדי שהלקוח לא יקליד ולא יניח את סכום הסימולציה.

**`StrategyResult`**

| שדה | טיפוס |
|---|---|
| `strategy_id` | `Literal["2x20000_1x10000","10x5000","25x2000","100x500"]` |
| `rank` | `StrictInt` `ge=1, le=4` |
| `allocations` | `BudgetAllocation[]` `min_length=1, max_length=2` |
| `point_estimate` | `float` `ge=0` |
| `lower_bound` | `float` `ge=0` |
| `upper_bound` | `float` `ge=0` |
| `bootstrap_iterations` | `StrictInt` `gt=0` |
| `evidence_level` | `Literal["high","medium","low"]` |
| `in_training_domain` | `Literal[True]` + `before`-validator (ד.0ב) |
| `warnings` | `ContractWarning[]` `max_length=0` |

**`BudgetAllocation`**

| שדה | טיפוס |
|---|---|
| `ad_budget` | `StrictInt` `gt=0` |
| `count` | `StrictInt` `gt=0` |
| `sample_size` | `StrictInt` `gt=0` |

⚠ שלושת שדות החיזוי ב-`StrategyResult` **אינם nullable** — ⛔ אין מצב OOD
בסימולטור (`IA.md` §6.1), ולכן אין תרחיש שבו הם `null`.

⚠ `in_training_domain` ב-P6 הוא **קבוע `true`** (`IA.md` §6.1): חמש רמות
התקציב שבשימוש — 500 · 2,000 · 5,000 · 10,000 · 20,000 — כולן בין 16
הערכים הנצפים, ויתר הפיצ'רים מוצבים מפרופיל חציוני. השדה נשאר לאחידות
ומתועד כמצב לא-נגיש, **לא כמצב מת**.

⚠ **`warnings` נשאר ב-`StrategyResult` ונעול כמערך ריק (`max_length=0`).**
`IA.md:375` מסמן את שדה 11 כנדרש **גם ב-P6**, ולכן ⛔ אין להסירו. אך שתי
האזהרות היחידות בחוזה בלתי-אפשריות כאן: `ood_feature_out_of_range` נשלל
על ידי `in_training_domain: Literal[True]`, ו-`unobserved_budget_level`
נשלל משום שחמש רמות התקציב הן מבין 16 הנצפים. `max_length=0` הופך את
העובדה הזו ל**אילוץ נאכף ובר-בדיקה** (`maxItems: 0` ב-OpenAPI) במקום
לשדה מת ושקט — אותו דפוס בדיוק כמו `Literal[True]` לצדו.
⚠ הוספת אזהרה כלשהי ל-P6 בעתיד היא **שינוי חוזה שעובר בשער**, לא תוספת
שקטה.

מכסה שדות חוזה **1, 2, 3, 4, 8, 9, 10, 11, 12**.

### ד.5 — `FollowupResponse`

```
stages:           AvailablePart[FunnelStage[]]     | PartUnavailable
calls_to_closed:  AvailablePart[CallsDistribution] | PartUnavailable
```

⚠ שני החלקים הם `required` — ⛔ אף אחד מהם אינו נשמט מהתשובה; חלק שנכשל
מיוצג כ-`PartUnavailable`, לא כהיעדר מפתח.

**`AvailablePart[T]`** — generic

| שדה | טיפוס |
|---|---|
| `status` | `Literal["available"]` |
| `data` | `T` |

**`PartUnavailable`**

| שדה | טיפוס |
|---|---|
| `status` | `Literal["unavailable"]` |
| `error` | `PartError` |

**`PartError`**

| שדה | טיפוס |
|---|---|
| `reason_code` | `Literal["data_unavailable","aggregation_mismatch"]` |
| `message` | `str` `min_length=1` |

ה-union נעשה על `status` (`Field(discriminator="status")`).

**`FunnelStage`**

| שדה | טיפוס |
|---|---|
| `stage_order` | `StrictInt` `ge=1, le=5` |
| `stage` | `Literal["followup_1","followup_2","followup_3","followup_4","followup_5"]` |
| `from_leads` | `StrictInt` `ge=0` |
| `to_leads` | `StrictInt` `ge=0` |
| `drop_rate` | `float` `ge=0, le=1` `\| null` |

`drop_rate` הוא **יחס 0–1, לא אחוז** — האחוז הוא שכבת תצוגה
(`20260901164904_views.sql`). `null` מותר כשהמכנה אפס דרך `nullif`.

⚠ **מיקום האילוץ:** `min_length=5, max_length=5` יושב על
**`AvailablePart[list[FunnelStage]].data`** — ⛔ לא על `stages`, שהוא ה-union
העוטף ואינו מערך. ה-view מייצר חמישה `union all` קבועים; אפס שורות הוא
שגיאת זמינות ⇒ `PartUnavailable`, ⛔ לא מערך קצר.

**`CallsDistribution`**

| שדה | טיפוס |
|---|---|
| `population_n` | `StrictInt` `gt=0` |
| `distribution` | `CallsBucket[]` `min_length=1` |

**`CallsBucket`**

| שדה | טיפוס |
|---|---|
| `calls` | `StrictInt` `ge=0` |
| `n` | `StrictInt` `gt=0` |

⛔ שתי משפחות ה-insights **אינן נושאות אף אחד מ-14 השדות** — הן אינן חיזוי.
בדיקת הכיסוי אינה מצפה לכך.

### ד.6 — `BudgetTiersResponse`

`tiers: TierRow[]` `max_length=4` — **מערך ריק מותר** (200).

⚠ `max_length=4` **נגזר מהחוזה**: ארבעת הזוגות החוקיים (כלל 21) ואיסור
הכפילות (כלל 22) אינם מאפשרים יותר מארבע שורות. האילוץ מופיע בארטיפקט
ולא רק ב-validator.

**`TierRow`**

| שדה | טיפוס |
|---|---|
| `tier_order` | `Literal[1,2,3] \| null` |
| `budget_tier` | `Literal["Low","Mid","High"] \| null` |
| `n_records` | `StrictInt` `gt=0` |
| `conversion_rate` | `float` `ge=0, le=1` `\| null` |

⚠ **שורה עם `tier_order=null` ו-`budget_tier=null` היא תשובה חוקית, לא
שגיאה** — אך **תרחיש עתידי מותנה**: ה-`CASE` ב-view נכתב **בלי `ELSE`** כדי
שערך בפער `1501–1999` יצוף כקבוצה משלו במקום להיבלע ב-"Mid".
⛔ **בנתונים היום אין רשומה כזו** — 16 ערכי ה-`ad_budget` הנצפים מדלגים מ-
1,500 ל-2,000, ו-`budget_tier_insight` מחזיר בפועל שלוש שורות בלבד
(Low 780 · Mid 1,717 · High 1,003 = 3,500). **רשומה עתידית** בטווח הזה
תוחזר בקבוצה שבה `tier_order` ו-`budget_tier` הם `null`, עם `count(*)` ו-
`avg(closed/nullif(num_leads,0))` שמחושבים לה ככל קבוצה אחרת — כלומר
`n_records` ו-`conversion_rate` **אמיתיים**. הסכמה חייבת לקבל את המקרה
מראש; ⛔ אין להפוך אותו לשגיאה ו⛔ אין לצפות לו בבדיקות על הנתונים הנוכחיים.

⛔ טייר בלי רשומות **אינו מוחזר כשורה מומצאת** — `group by` על שורות קיימות.
שתי הבחנות נפרדות: טייר בלי רשומות (אין שורה) מול קבוצה קיימת שאינה
משויכת לטייר רגיל (שורה מלאה).

### ד.7 — קטלוג רכיבי המשנה וסכמות השגיאה

⛔ **אין ברשימות שמות בלבד.** כל שדה נעול בטיפוס, nullability ומגבלה.
המודלים שהוגדרו כבר בטבלאות ד.1–ד.6 אינם חוזרים כאן.

**`ContractWarning`** — alias ל-discriminated union לפי `code`:
`OODWarning | UnobservedBudgetWarning`, `Field(discriminator="code")`.
⛔ **אין להשתמש בשם `Warning`** — הוא builtin של Python (מחלקת הבסיס של
`UserWarning` ואחיותיה), ומודל Pydantic בשם הזה מצל עליו בכל מודול שמייבא
את הסכמות.

**`OODWarning`**

| שדה | טיפוס |
|---|---|
| `code` | `Literal["ood_feature_out_of_range"]` |
| `message` | `str` `min_length=1` |
| `feature` | `Literal[…]` — **13 שמות פיצ'רי הקלט** |
| `value` | `float` |
| `min` | `float` |
| `max` | `float` |

⛔ **`feature` אינו `str` חופשי.** ה-enum נגזר מ-
`MODEL_INPUT_FEATURES["P2"]` (זהה ל-P3 ול-P4, 13 שמות, אומת בסעיף ב ממצא 1)
— ⛔ לא מוקלד ידנית. אזהרת OOD על שם שדה שאינו פיצ'ר קלט היא **שגיאת שרת**,
לא הודעה למשתמש. ⚠ `MODEL_INPUT_FEATURES["P6"]` **אינו** המקור — הוא מונה
14 שדות כולל `purchased`, שאינו קלט משתמש.

**`UnobservedBudgetWarning`**

| שדה | טיפוס |
|---|---|
| `code` | `Literal["unobserved_budget_level"]` |
| `message` | `str` `min_length=1` |
| `feature` | `Literal["ad_budget"]` |
| `value` | `float` `gt=0` |

**`IntervalDetails`**

| שדה | טיפוס |
|---|---|
| `nominal_coverage` | `float` `ge=0, le=1` |
| `measured_coverage` | `float` `ge=0, le=1` |

**`RegressionMetrics`** (P2 · P6) — שני תת-בלוקים, שניהם `required`:

| בלוק | שדה | טיפוס |
|---|---|---|
| `cv` | `mean_mae` · `mean_rmse` | `float` `ge=0` |
| `cv` | `mean_r2` | `float` `le=1` |
| `holdout` | `mae` · `rmse` | `float` `ge=0` |
| `holdout` | `r2` | `float` `le=1` |

**`ClassificationMetrics`** (P3 · P4) — שני תת-בלוקים, שניהם `required`:

| בלוק | שדה | טיפוס |
|---|---|---|
| `cv` | `mean_roc_auc` · `mean_pr_auc` | `float` `ge=0, le=1` |
| `cv` | `mean_brier` | `float` `ge=0, le=1` |
| `cv` | `mean_log_loss` | `float` `ge=0` |
| `holdout` | `roc_auc` · `pr_auc` · `brier` | `float` `ge=0, le=1` |
| `holdout` | `log_loss` | `float` `ge=0` |

⚠ `r2` חסום מלמעלה ב-1 ו⛔ **אינו** חסום מלמטה — R² שלילי הוא ערך לגיטימי
למודל גרוע מהממוצע. `log_loss` חסום מלמטה ב-0 ואינו חסום מלמעלה.

**`ErrorDetail`** (401 · 403 · 500 · 503)

| שדה | טיפוס |
|---|---|
| `detail` | `str` `min_length=1` |

**`HTTPValidationError`** (422 בלבד)

| שדה | טיפוס |
|---|---|
| `detail` | `ValidationErrorItem[]` |

**`ValidationErrorItem`** — ⛔ **אינו** ברירת המחדל של FastAPI:

| שדה | טיפוס |
|---|---|
| `loc` | `(str \| StrictInt)[]` `min_length=1` |
| `msg` | `str` `min_length=1` |
| `type` | `str` `min_length=1` |

⚠ **ברירת המחדל של FastAPI רחבה יותר ואינה יציבה.** אומת בסביבת הפרויקט:
גוף 422 בפועל מכיל `['input','loc','msg','type']`, וסכמת ה-OpenAPI
האוטומטית מכילה `['ctx','input','loc','msg','type']` — חמישה שדות,
ו-`ctx` מופיע רק לחלק מסוגי השגיאה.

**ההכרעה: חוזה FunnelIQ מצומצם ויציב — `loc`/`msg`/`type` בלבד.**
⛔ אין לאמץ את מבנה FastAPI, שמשתנה בין גרסאות וחושף את ערך הקלט
(`input`) בגוף השגיאה.

⚠ **המנגנון אומת:** כאשר `HTTPValidationError` מקומי מופנה במפורש דרך
`responses={422: {"model": HTTPValidationError}}`, FastAPI פולט
ל-`components.schemas` **רק** את `HTTPValidationError` ו-
`ValidationErrorItem` שלנו; הסכמה האוטומטית עם `ctx`/`input` **אינה מופיעה
כלל**, ואין התנגשות שמות.

**חובת פאזה 9 — מוצהרת כאן:** handler ל-`RequestValidationError` שמנרמל את
`exc.errors()` למבנה הזה ומסיר `input` ו-`ctx`. ⛔ בלי ה-handler הגוף בפועל
לא יתאים לחוזה שננעל כאן.

**רשימת הרכיבים** — ⛔ ללא מספר, ר' האזהרה שמיד לאחריה: `FunnelInput` · `ContractWarning` ·
`OODWarning` · `UnobservedBudgetWarning` · `IntervalDetails` ·
`RegressionMetrics` · `ClassificationMetrics` · `StrategyResult` ·
`BudgetAllocation` · `FunnelStage` · `CallsDistribution` · `CallsBucket` ·
`AvailablePart` · `PartUnavailable` · `PartError` · `TierRow` ·
`ErrorDetail` · `HTTPValidationError` · `ValidationErrorItem`.

⚠ ⛔ **אין לנעול את מספר הרכיבים ב-`components.schemas`.** המספר תלוי באופן
שבו Pydantic מייצא unions ו-generics — `AvailablePart` פרמטרי עשוי להיפלט
כשם מפורק לכל פרמטריזציה, או להיות inline. הדרישה היא **נגישות**: חמש
משפחות התגובה, כל הסכמות הנגישות מהן בסגור ההפניות, ושתי סכמות השגיאה,
מיוצאות ב-`components.schemas` או דרך `oneOf`/`$ref` תקינים.

### ד.8 — אינווריאנטים בין-שדות ב-`LtvPrediction` ו-`PropensityPrediction`

⚠ **JSON Schema שנפלט מ-Pydantic אינו מבטא תלות מותנית בין שדות** — לא
`if/then` ולא `dependentSchemas`. לכן האינווריאנטים נאכפים ב-
**`model_validator` על מודלי התגובה** ב-`app/schemas.py`, ונבדקים
ב-`tests/test_api_contract.py` ב**אינסטנציאציה ישירה** של המודל: צירוף סותר
⇒ `ValidationError`. ⛔ אין כאן HTTP, אין Auth ואין טעינת מודל — בדיקת סכמה
לכל דבר.

| # | צירוף | דין |
|---|---|---|
| 1 | `in_training_domain=false` **+** שדה חיזוי מספרי (לא `null`) | ⛔ נדחה |
| 2 | `in_training_domain=false` **+** `warnings` בלי `OODWarning` | ⛔ נדחה |
| 3 | `in_training_domain=true` **+** `OODWarning` קיים | ⛔ נדחה |
| 4 | `in_training_domain=true` **+** שדה חיזוי `null` | ⛔ נדחה |
| 5 | `evidence_level="low"` **+** `warnings` בלי `UnobservedBudgetWarning` | ⛔ נדחה |
| 6 | `evidence_level=null` **+** `UnobservedBudgetWarning` קיים | ⛔ נדחה |

שדות החיזוי לעניין 1 ו-4: `point_estimate`/`lower_bound`/`upper_bound`
ב-`LtvPrediction` · `event_probability`/`propensity_band` ב-
`PropensityPrediction`.

**שני ביקונדיציונלים סימטריים:**

| זוג | קשר |
|---|---|
| 2 ו-3 | `in_training_domain=false` ⟺ קיימת `OODWarning` |
| 5 ו-6 | `evidence_level="low"` ⟺ קיימת `UnobservedBudgetWarning` |

השני נובע מ-D2, שם `low` מופעל אך ורק על ידי תקציב פנימי שלא נצפה.
⚠ שני הקשרים **בלתי תלויים זה בזה** (D2/D5) — רשומה יכולה לשאת את שתי
האזהרות יחד, אחת מהן, או אף אחת.

⛔ **ששת האינווריאנטים לעיל אינם חלים על `StrategyResult`**: שם
`in_training_domain: Literal[True]`, `warnings` נעול `max_length=0`, ושדות
החיזוי אינם nullable — הצירופים אינם ניתנים לביטוי.

### ד.8ב — אינווריאנטים של `BudgetSimulation.strategies`

`min_length=4, max_length=4` נאכף בסכמה (`minItems`/`maxItems`). ארבעת
הכללים הבאים ⛔ **אינם ניתנים לביטוי ב-JSON Schema** ולכן יושבים ב-
`model_validator` על `BudgetSimulation`, ונבדקים באינסטנציאציה ישירה:

| # | כלל |
|---|---|
| 7 | `strategy_id` הם **בדיוק** ארבעת המזהים הנעולים, בלי כפילות ובלי חוסר |
| 8 | `rank` ייחודי ומכסה בדיוק את `{1,2,3,4}` |
| 9 | המערך **מסודר לפי `rank` עולה** — `strategies[i].rank == i+1` |
| 10 | לכל אסטרטגיה, זוגות `(ad_budget, count)` ב-`allocations` **זהים בדיוק ובסדר** ל-`STRATEGY_ALLOCATIONS[strategy_id]` |

⚠ **כלל 10 סוגר פער אמיתי:** בלעדיו מודל תקין לחלוטין יכול לשאת
`strategy_id="100x500"` עם ההרכב של `10x5000` — מזהה נכון, `rank` נכון,
אורך נכון, והרכב של אסטרטגיה אחרת. כללים 7–9 אינם קושרים בין המזהה
לתוכן.

⚠ **סכום ה-50,000 נגזר, לא נבדק כאן.** אם `allocations` זהים ל-
`STRATEGY_ALLOCATIONS[strategy_id]`, וקריטריון 11 מאמת שהקבוע מסתכם
ל-50,000 לכל אסטרטגיה — הסכום בתגובה מובטח **טרנזיטיבית**. ⛔ לכן אין
לוותר על קריטריון 11 מתוך מחשבה ש-8ב מכסה אותו: הם שתי חוליות של אותה
שרשרת, ובלי הראשונה השנייה מאמתת מול קבוע שאיש לא בדק.

⛔ **כלל 10 אינו מכסה את `sample_size`.** `STRATEGY_ALLOCATIONS` מחזיק
זוגות `(ad_budget, count)` בלבד; `sample_size` מגיע מ-`P6_simulation.json
→ levels[*].n`, וקריאת ארטיפקט ב-`app/schemas.py` סותרת את D1. **אימות
`sample_size` מול הארטיפקט הוא חובת פאזה 9** — מוצהר כאן, לא נגזר.

⚠ **מיקום מכוון:** ארבעת אלה הם אינווריאנטים של **מודל התגובה**, ולכן הם
כאן ולא בקריטריון 11. קריטריון 11 בודק **parity של קבוע מול ארטיפקטים**
(`STRATEGY_ALLOCATIONS` מול `P6_simulation.json` ומול `IA.md` §6) — נושא
בדיקה אחר לגמרי. ערבוב השניים היה יוצר בדיקה שנכשלת משתי סיבות שונות
בלי להבחין ביניהן.

⚠ כלל 9 מייתר לכאורה את `rank`, שכן הוא נגזר מהאינדקס. השדה **נשאר**:
`IA.md` §6 מציג דירוג מפורש, ולקוח שממיין מחדש או שמציג תת-קבוצה זקוק
לערך ולא למיקום. הכלל מבטיח ששני המקורות לעולם לא יסתרו.

### ד.8ג — אינווריאנטים פנימיים נוספים

**הכלל שקובע שיוך:** אינווריאנט הנגזר **אך ורק מה-payload עצמו או מקבועים
סטטיים** שייך לפאזה 8. כל דבר שדורש קריאת ארטיפקט, Supabase או ספירה
עצמאית — פאזה 9.

| # | מודל | כלל |
|---|---|---|
| 11 | `LtvPrediction` | `lower_bound ≤ point_estimate ≤ upper_bound` — כששלושתם אינם `null` |
| 12 | `StrategyResult` | `lower_bound ≤ upper_bound`. ⚠ ⛔ **אין לדרוש** `point` בתוך הטווח — `P6_simulation.json` שומר `point`, `lower` ו-`upper` שחושבו בנפרד, ואין הצהרה בפאזה 6 שהנקודה נופלת בהכרח בין אחוזוני ה-Bootstrap |
| 13 | `PropensityPrediction` | `propensity_band` תואם ל-`event_probability` מול `base_rate` לפי ספי ד.3 — כששניהם אינם `null` |
| 14 | `BudgetSimulation` | `strategies[].evidence_level` תואם ל-`min(allocations[].sample_size)` לפי ספי D2 (`n≥200`/`50≤n<200`/`n<50`) |
| 15 | `OODWarning` | `min ≤ max`, ו-`value` **מחוץ** ל-`[min, max]` — אזהרת OOD שערכה בתוך הטווח היא סתירה. `feature` נעול ל-13 שמות הקלט (ד.7) |
| 16 | `AvailablePart[list[FunnelStage]]` | חמשת הזוגות `(stage_order, stage)` בדיוק ובסדר: `(1,followup_1)` … `(5,followup_5)` |
| 17 | `FunnelStage` | `to_leads ≤ from_leads` |
| 18 | `AvailablePart[list[FunnelStage]]` | **שרשור**: `data[i].to_leads == data[i+1].from_leads` לכל `i` ב-0..3 |
| 19 | `FunnelStage` | `drop_rate is null` **אם ורק אם** `from_leads == 0`; אחרת `drop_rate ≈ 1 − to_leads/from_leads` בסובלנות `1e-9` |
| 20 | `CallsDistribution` | ערכי `calls` **ייחודיים**, ו-`sum(distribution[].n) == population_n` |
| 21 | `TierRow` | הזוג `(tier_order, budget_tier)` הוא אחד מ-`(1,Low)` · `(2,Mid)` · `(3,High)` · `(null,null)` |
| 22 | `BudgetTiersResponse` | ⛔ **בלי כפילות** — כל זוג מופיע לכל היותר פעם אחת ב-`tiers[]` |

⚠ **מיקום מכוון (16–22):** אינווריאנט נבדק במודל ש**רואה** אותו. זוג
`(tier_order, budget_tier)` נראה מ-`TierRow` (21), אבל **כפילות** נראית רק
מהרשימה — ולכן היא ב-`BudgetTiersResponse` (22). באותו אופן, סדר ואורך
השלבים (16) ושרשור (18) הם כללי **רשימה** ולא כללי שורה, בעוד
`to_leads ≤ from_leads` (17) ו-`drop_rate` (19) הם כללי שורה.

⚠ **19–17–18 נגזרים ממבנה `followup_insight` שאומת** (סעיף ב, ממצא 17):
ה-view בונה חמישה `union all` שבהם `from_leads` של שלב `i+1` הוא בדיוק
`to_leads` של שלב `i`, ו-`drop_rate = 1 − to/nullif(from, 0)`. ⛔ שלושתם
נגזרים **מה-payload בלבד** ולכן פאזה 8; ⛔ אין כאן קריאה ל-Supabase.

⚠ **סובלנות `1e-9` ולא שוויון מדויק** — `drop_rate` הוא `numeric` שעבר
המרה ל-`float`; השוואה מדויקת הייתה נכשלת על עיגול. אותה סובלנות שנקבעה
בפאזה 3 ליחסי 0–1.

⚠ **כלל 20 אינו בדיקת הסגירות של פאזה 9.** כאן זו **עקביות פנימית של
התגובה** — הסכום המוצהר מול הפירוט שבצדו. אימות מול `count="exact"` עצמאי
ב-Supabase (`IA.md` §7.1) הוא **פאזה 9**, והוא זה שמזהה קטיעה.

⚠ **כלל 14 נשען על ספים שאינם בארטיפקט** — הם החלטת פאזה 7 (D2). לכן הם
קבוע סטטי ב-`app/schemas.py`, ⛔ לא ערך נקרא.

⛔ **מה שאינו כאן:** `top_two_overlap` מול חפיפת טווחים בפועל · `sample_size`
מול `P6_simulation.json` · `model_version` מול `meta.json` · סגירות מול
Supabase. כולם דורשים ארטיפקט או רשת ⇒ **פאזה 9**.

---

## ה. מטריצת 14 השדות → משפחת תגובה

| # | שדה | `LtvPrediction` | `PropensityPrediction` | `BudgetSimulation` |
|---|---|---|---|---|
| 1 | `point_estimate` | ✅ | — | ✅ `StrategyResult` |
| 2 | `lower_bound` | ✅ | — | ✅ `StrategyResult` |
| 3 | `upper_bound` | ✅ | — | ✅ `StrategyResult` |
| 4 | `interval_method` | ✅ | — | ✅ |
| 5 | `event_probability` | — | ✅ | — |
| 6 | `base_rate` | — | ✅ | — |
| 7 | `propensity_band` | — | ✅ | — |
| 8 | `evidence_level` | ✅ | ✅ | ✅ `StrategyResult` |
| 9 | `sample_size` | — | — | ✅ `BudgetAllocation` |
| 10 | `in_training_domain` | ✅ | ✅ | ✅ `StrategyResult` |
| 11 | `warnings` | ✅ | ✅ | ✅ `StrategyResult` |
| 12 | `model_version` | ✅ | ✅ | ✅ |
| 13 | `calibration_status` | — | ✅ | — |
| 14 | `calibration_method` | — | ✅ | — |

✅ **כל 14 השדות מכוסים** על ידי שלוש משפחות החיזוי.

### ה.1 — מפת השדות המלאה

⛔ הרשימה הקודמת מנתה חלק מהשדות הנוספים בלבד והשמיטה את שתי משפחות
ה-insights. להלן **כל שדה בכל סכמה**, לפי נתיב JSON מהשורש — זו המפה
שקריטריון 5 נבדק מולה.

**אלגוריתם ההשוואה — קנוני, אחד בלבד:**

1. נספר **כל `property` בעל שם**, כולל containers — `metrics`,
   `interval_details`, `strategies`, `warnings`, `tiers`, `stages`,
   `calls_to_closed`, `detail`. ⛔ לא עלים בלבד.
2. **`property` של מערך נספר בשמו העצמו** — `strategies`, `warnings`,
   `tiers`, `detail`. ⛔ **בלי `[]`**.
3. **`[]` מופיע רק בדרך לילד** — `strategies[].rank` ·
   `tiers[].n_records` · `detail[].msg`. מערך של סקלרים אין לו ילדים ולכן
   לעולם אינו מקבל `[]`: `bootstrap_percentiles` בלבד.
4. ילדים נכתבים בנתיב מלא מהשורש: `metrics.cv.mean_mae` ·
   `calls_to_closed.data.population_n`.
5. ⛔ אין wildcards.
6. **`root-resolved closure` לכל root.** ⛔ לא רשימות component-local
   נפרדות ו⛔ לא קבוצה גלובלית אחת. שמונת ה-roots הם: `FunnelInput` ·
   חמש משפחות התגובה · `ErrorDetail` · `HTTPValidationError`. לכל אחד
   בונים את המפה כך:
   - ⛔ **שם ה-root אינו חלק מהנתיב.** הנתיב מתחיל מה-`property` הראשון
     שמתחת לו: ב-`HTTPValidationError` הנתיבים הם `detail` ו-
     `detail[].loc`, ⛔ לא `HTTPValidationError.detail`.
   - **הסריקה יורדת דרך שלושה מנגנונים בלבד:** `properties` של אובייקט ·
     `items` של מערך · `$ref`/`oneOf`/`anyOf`. ⛔ ערכי scalar בתוך
     `prefixItems` **אינם נספרים** — הם אינם `properties` בעלי שם, ולכן
     `bootstrap_percentiles` נספר פעם אחת ואין לו ילדים.
   - פותחים **`$ref` רקורסיבית**, ומצרפים את שמות ה-`properties` בנתיב
     מלא מה-root.
   - **`oneOf` ו-`anyOf`: מאחדים את נתיבי כל הענפים** לקבוצה אחת. לכן
     `warnings[].min` ו-`warnings[].max` נכללים — הם קיימים בענף
     `OODWarning` ולא בענף `UnobservedBudgetWarning`; אותו דבר ל-
     `stages.data` מול `stages.error`.
   - **מניעת לולאות:** נשמרת קבוצת `$ref` שכבר נפתחו **בנתיב הנוכחי**;
     `$ref` שחוזר בנתיב שלו נחתך ואינו מורחב שוב. ⚠ בחוזה הזה אין
     רקורסיה בפועל, והכלל קיים כדי שהאלגוריתם יהיה טוטלי.
7. ההשוואה היא **פר-root ובשני הכיוונים** — כל root מול המפה שלו.
   ⛔ לא קבוצה גלובלית: אחרת שדה שנפל ממשפחה אחת "מכוסה" על ידי מופע
   באחרת.

⚠ **מכאן ש-`LtvPrediction` ו-`PropensityPrediction` כוללות במפה שלהן גם
`warnings[].code` · `warnings[].message` · `warnings[].feature` ·
`warnings[].value` · `warnings[].min` · `warnings[].max`**, ו-
`BudgetSimulation` כוללת את אותם נתיבים תחת `strategies[].warnings` —
**גם כאשר `max_length=0`**, כי המפה מתארת את **הסכמה**, לא את הערכים
האפשריים.

⚠ הכלל הזה הוא **הגדרת קריטריון 5**. בלעדיו ההשוואה תלויה במימוש ואינה
דטרמיניסטית.

**בקשה — `FunnelInput`** (שלושת נתיבי `POST`): `ad_budget` · `num_leads` ·
`leads_answered` · `followup_1` · `followup_2` · `followup_3` ·
`followup_4` · `followup_5` · `not_closed` · `closed` · `calls_to_closed` ·
`calls_to_not_closed` · `customer_acquisition_cost` — 13 שדות, ⛔ אף אחד
מהם אינו משדות החוזה (הם קלט, לא תגובה).

**`LtvPrediction`**

| נתיב | מ-14? |
|---|---|
| `point_estimate` · `lower_bound` · `upper_bound` · `interval_method` | ✅ 1,2,3,4 |
| `evidence_level` · `in_training_domain` · `warnings` · `model_version` | ✅ 8,10,11,12 |
| `interval_details` · `interval_details.nominal_coverage` · `interval_details.measured_coverage` | — |
| `model_algorithm` | — |
| `metrics` · `metrics.cv` · `metrics.cv.mean_mae` · `metrics.cv.mean_rmse` · `metrics.cv.mean_r2` | — |
| `metrics.holdout` · `metrics.holdout.mae` · `metrics.holdout.rmse` · `metrics.holdout.r2` | — |
| `warnings[].code` · `warnings[].message` · `warnings[].feature` · `warnings[].value` · `warnings[].min` · `warnings[].max` | — |

**`PropensityPrediction`**

| נתיב | מ-14? |
|---|---|
| `event_probability` · `base_rate` · `propensity_band` | ✅ 5,6,7 |
| `evidence_level` · `in_training_domain` · `warnings` · `model_version` | ✅ 8,10,11,12 |
| `calibration_status` · `calibration_method` | ✅ 13,14 |
| `model_algorithm` | — |
| `metrics` · `metrics.cv` · `metrics.cv.mean_roc_auc` · `metrics.cv.mean_pr_auc` · `metrics.cv.mean_brier` · `metrics.cv.mean_log_loss` | — |
| `metrics.holdout` · `metrics.holdout.roc_auc` · `metrics.holdout.pr_auc` · `metrics.holdout.brier` · `metrics.holdout.log_loss` | — |
| `warnings[].code` · `warnings[].message` · `warnings[].feature` · `warnings[].value` · `warnings[].min` · `warnings[].max` | — |

**`BudgetSimulation`**

| נתיב | מ-14? |
|---|---|
| `interval_method` · `model_version` | ✅ 4,12 |
| `total_budget` · `bootstrap_percentiles` · `top_two_overlap` · `model_algorithm` | — |
| `metrics` · `metrics.cv` · `metrics.cv.mean_mae` · `metrics.cv.mean_rmse` · `metrics.cv.mean_r2` | — |
| `metrics.holdout` · `metrics.holdout.mae` · `metrics.holdout.rmse` · `metrics.holdout.r2` | — |
| `strategies` | — |
| `strategies[].point_estimate` · `strategies[].lower_bound` · `strategies[].upper_bound` | ✅ 1,2,3 |
| `strategies[].evidence_level` · `strategies[].in_training_domain` · `strategies[].warnings` | ✅ 8,10,11 |
| `strategies[].strategy_id` · `strategies[].rank` · `strategies[].bootstrap_iterations` | — |
| `strategies[].allocations` | — |
| `strategies[].allocations[].sample_size` | ✅ 9 |
| `strategies[].allocations[].ad_budget` · `strategies[].allocations[].count` | — |
| `strategies[].warnings[].code` · `strategies[].warnings[].message` · `strategies[].warnings[].feature` · `strategies[].warnings[].value` · `strategies[].warnings[].min` · `strategies[].warnings[].max` | — |

**`FollowupResponse`** — ⛔ אף שדה מ-14

`stages` · `stages.status` · `stages.data` · `stages.data[].stage_order` ·
`stages.data[].stage` · `stages.data[].from_leads` ·
`stages.data[].to_leads` · `stages.data[].drop_rate` ·
`stages.error` · `stages.error.reason_code` · `stages.error.message` ·
`calls_to_closed` · `calls_to_closed.status` · `calls_to_closed.data` ·
`calls_to_closed.data.population_n` ·
`calls_to_closed.data.distribution` ·
`calls_to_closed.data.distribution[].calls` ·
`calls_to_closed.data.distribution[].n` ·
`calls_to_closed.error` · `calls_to_closed.error.reason_code` ·
`calls_to_closed.error.message`

⚠ `data` ו-`error` **אינם מופיעים יחד** — הם ענפי ה-union לפי `status`.

**`BudgetTiersResponse`** — ⛔ אף שדה מ-14

`tiers` · `tiers[].tier_order` · `tiers[].budget_tier` ·
`tiers[].n_records` · `tiers[].conversion_rate`

**שני ענפי `ContractWarning`** — ⛔ אינם roots נפרדים; הם נפתחים לתוך
המפה של כל משפחה שנושאת `warnings` (סעיף 6 לעיל):

| ענף | שדות |
|---|---|
| `OODWarning` | `code` · `message` · `feature` · `value` · `min` · `max` |
| `UnobservedBudgetWarning` | `code` · `message` · `feature` · `value` |

⛔ `min` ו-`max` קיימים ב-`OODWarning` **בלבד** — ואיחוד הענפים מכניס
אותם למפה, כי המפה מתארת את **צורת הסכמה**, לא ערך יחיד.

**סכמות השגיאה**

**`ErrorDetail`** — `detail`

**`HTTPValidationError`** — `detail` · `detail[].loc` · `detail[].msg` ·
`detail[].type`

⚠ שם ה-root אינו בנתיב (סעיף 6).

⛔ **שתי משפחות ה-insights אינן נושאות אף אחד מ-14 השדות** — הן אינן חיזוי.
כיסוי 14 השדות נבדק מול שלוש משפחות החיזוי בלבד.

---

## ו. מקורות אמת משותפים

### ו.1 — `MODEL_INPUT_FEATURES`

**המצב היום הוא חריגה מ-`CLAUDE.md`**, שקובע ש-`app/features.py` הוא מקור
האמת לפיצ'רים: `model_feature_columns()` — הפונקציה שקובעת בפועל מה נכנס
ל-`meta.json.feature_columns` — יושבת ב-`scripts/train.py:171-176`.

**התיקון: העברה, לא הוספה.** קבוע חדש לצד הפונקציה הקיימת היה יוצר שני
מקורות במקום אחד.

| פעולה | פירוט |
|---|---|
| מועבר | `DROPPED_COLLINEAR` · `model_feature_columns()` · `STRATEGY_ALLOCATIONS` ⇐ `scripts/train.py` ⇒ `app/features.py` |
| נחשף | `MODEL_INPUT_FEATURES = {task: model_feature_columns(task)}` לארבע המשימות |
| `scripts/train.py` | **מייבא ומייצא-מחדש** — `train.py:39` כבר מייבא מ-`app.features`, ההעברה הולכת עם כיוון התלות הקיים |

⛔ **`DROPPED_COLLINEAR` חייב לעבור יחד עם הפונקציה.** אומת:
`scripts/train.py:168` מגדיר אותו, `:176` `model_feature_columns` **תלויה
בו**, ו-`tests/test_train.py:269` ניגש אליו כ-`tr.DROPPED_COLLINEAR`.
העברת הפונקציה לבדה **שוברת אותה**; העברה בלי re-export **שוברת בדיקה של
פאזה 6**. לכן `scripts/train.py` מייבא אותו ומשאיר אותו נגיש בשמו,
ו-`tr.DROPPED_COLLINEAR` ממשיך לעבוד ללא שינוי בבדיקות.

⚠ **מיקום:** לצד `COLLINEAR_TRIO` שכבר יושב ב-`app/features.py:70` — שניהם
נוגעים לאותה שלישייה, ופיצולם בין שני קבצים הוא בדיוק המצב שההעברה מתקנת.

⛔ **`FEATURES` אינה משתנה** — היא רשימת המועמדים **לפני** צמצום
`COLLINEAR_TRIO`, ו-`tests/test_features.py` + `docs/feature_matrix.md`
נשענים עליה. שינוי שלה שובר בדיקה של פאזה 5.

⚠ **העברה טהורה: אפס שינוי התנהגות, אפס אימון מחדש.** ⛔ פאזה 8 **אינה
בונה ואינה משנה** את קובצי `models/*.meta.json` — היא רק בודקת parity
מולם; לכן אין כאן הבטחת זהות בייט-לבייט, שאינה ניתנת לאימות בפאזה זו.

ה-API **אינו צריך** לייבא מ-`scripts/train.py` — טכנית הוא יכול, אך הייבוא
גורר את `xgboost`/`lightgbm`/`catboost` ומגדיל את זמן העלייה ואת טביעת
הזיכרון של השירות. זו החלטת תלות ומשאבים, והיא הסיבה שההעברה נדרשת.

`FunnelInput` נבדק מול `MODEL_INPUT_FEATURES` של **P2/P3/P4 בלבד** —
שלושתם 13 שדות זהים ובאותו סדר. `MODEL_INPUT_FEATURES["P6"]` מכיל 14 שדות
(כולל `purchased`) ו**אינו סכמת בקשת משתמש**.

### ו.2 — `STRATEGY_ALLOCATIONS`

מקור האמת היחיד להרכב האסטרטגיות:
`{"2x20000_1x10000":[(20000,2),(10000,1)], "10x5000":[(5000,10)],
"25x2000":[(2000,25)], "100x500":[(500,100)]}`.

⚠ **`P6_simulation.json` אינו מכיל `count`** — רק `levels[*].n`. לכן בדיקת
ה-parity **מתפצלת לשתיים**:

| מול | נבדק |
|---|---|
| `P6_simulation.json` | אותם `strategy_id`, אותן רמות `ad_budget` |
| `expected` עצמאי מ-`IA.md` §6 | ה-`count` המדויק, ההרכב המדויק, וסכום `level × count = 50,000` לכל אסטרטגיה |

⛔ **אין לפרסר את `strategy_id`** כדי להסיק `count`.

---

## ז. מפת אחריות מול `IA.md` §9.1

| שייך ל | פריטים |
|---|---|
| **חוזה — פאזה 8** | סכמות בקשה ותשובה · OOD פר-פאנל · `warnings` · תשובה ריקה · כשל חלקי · קודי 401/403/422/500/503 · הצהרת `security` · enums ו-nullability · `propensity_band` · `evidence_level` · `base_rate` · מדדים, גרסאות ו-`interval_details` |
| **שרת — פאזה 9** | חיבור ה-router ל-`app.main.app` · מימוש ששת הנתיבים · `Depends(current_user)` ו-JWT בפועל · טעינת `joblib`/`meta.json`/`metrics.json` · חיזוי, זיהוי OOD ויצירת `warnings` בפועל · קריאות Supabase · עימוד `calls_to_closed` ואימות סגירות מול ספירה עצמאית · אגרגציות · בדיקות HTTP אמיתיות · projection מנורמל מול החוזה הנעול |
| **לקוח — פאזה 11** | `loading` · `retry` · מונה הדור (§9.4) · ניווט 401/403 בדפדפן · Login ו-`GET /api/config` (קיימים מפאזה 4) · בורר ה-`prefill` (supabase-js ישירות, ⛔ לא דרך ה-API) · נוסחי `empty` · רינדור פאנלים וגרפים · נגישות, RTL ושפת הגרפים (§10) |

⚠ חמש משפחות התגובה **אינן יכולות לכסות לבדן את `IA.md` §9.1** — חלקו הוא
התנהגות לקוח. פאזה 8 ממפה במפורש מה בחוזה ומה לא, ואינה מנסה למשוך מצבי UI
לתוך הסכמה.

---

## ח. תוצרים וסדר ביצוע

| # | קובץ | פעולה |
|---|---|---|
| 1 | `app/features.py` | **העברת** `DROPPED_COLLINEAR` · `model_feature_columns()` · `STRATEGY_ALLOCATIONS`; חשיפת `MODEL_INPUT_FEATURES` |
| 2 | `scripts/train.py` | ייבוא ו**ייצוא-מחדש** במקום הגדרה — אפס שינוי התנהגות. ⚠ **1 ו-2 הם שינוי אטומי אחד** |
| 3 | `app/schemas.py` | **חדש** — כל מודלי הבקשה והתגובה |
| 4 | `scripts/export_openapi.py` | **חדש** — אפליקציית חוזה מבודדת, ייצוא דטרמיניסטי |
| 5 | `docs/api/openapi.json` | **הארטיפקט הנעול** |
| 6 | `tests/test_api_contract.py` | **חדש** — 19 קבוצות בדיקה סטטיות (סעיף ט) |
| 7 | `docs/IA.md` · `docs/planning/SPEC.md` | `POST` → `GET` (שני מופעים + אחד) |
| 8 | `ROADMAP.html` | סטטוסים וראיות לכל checkpoint |

⚠ `docs/planning/PHASE7.md` עודכן **בשלב התכנון** (חידוד `offline`, D2) ואינו
תוצר ביצוע.

⛔ `app/main.py` **אינו משתנה**. ⛔ `app/auth.py` **אינו משתנה** (D13 היא
חובת פאזה 9). ⛔ `FEATURES` אינה משתנה. ⛔ `codex-history.md` אינו נגוע.

**סדר:** 1–2 לפני 3 (הסכמה נשענת על `MODEL_INPUT_FEATURES`) · 3 לפני 4 ·
4 לפני 5 · 6 אחרי 5 · 7 בכל שלב · 8 מיד אחרי כל checkpoint שאומת.

---

## ט. קריטריוני קבלה — 19 קבוצות בדיקה סטטיות

⚠ **"קבוצת בדיקה" ולא "בדיקה"** — כל סעיף מכיל כמה מקרי בדיקה. קריטריון 8ב
לבדו מרכז **22 אינווריאנטים**: 6 מד.8 · 4 מד.8ב · 12 מד.8ג. ⛔ אין לכנות
את כולם "צירופים סותרים" — חלקם כללי תקינות חיוביים.

| # | בדיקה |
|---|---|
| 1 | ייצוא חוזר של OpenAPI **זהה** ל-`docs/api/openapi.json` (drift) |
| 2 | קיימים **בדיוק ששת** הנתיבים העסקיים, במתודות שננעלו (שלושה `POST`, שלושה `GET`) |
| 2א | **חתימת כל נתיב** (ד.0א): `responses["200"]` הוא `$ref` ישיר לסכמה הנכונה · ל-`POST` יש `requestBody` עם `required: true` המפנה ל-`FunnelInput` · ל-`GET` ⛔ **אין** `requestBody` ו⛔ **אין** `parameters` |
| 3 | חמש משפחות התגובה, כל הסכמות הנגישות מהן בסגור ההפניות, ושתי סכמות השגיאה — מיוצאות ב-`components.schemas` או דרך `oneOf`/`$ref` תקינים. ⛔ בלי נעילת מספר רכיבים (ד.7) |
| 4 | כל **14** שדות המינימום ממופים לפחות למשפחת חיזוי אחת |
| 5 | **מפת ה.1 מתאימה ל-OpenAPI בשני הכיוונים, פר-root**, לפי האלגוריתם הקנוני: `root-resolved closure` לשמונת ה-roots · `$ref` נפתח רקורסיבית · נתיבי ענפי `oneOf`/`anyOf` **מאוחדים** · `property` של מערך בשמו העצמו · `[]` רק בדרך לילד · ⛔ בלי wildcard |
| 5א | סגור ה-`warnings` נכלל בכל משפחה שנושאת אותו — כולל `warnings[].min`/`max` מענף `OODWarning`, וכולל `strategies[].warnings` על ילדיו **גם תחת `max_length=0`** |
| 6 | enums, nullability ו-discriminator נכונים: `interval_method` בדיוק שני ערכים · `evidence_level` nullable ב-P2/P3/P4 ולא ב-P6 · `warnings` נפלט כ-`oneOf` + `discriminator` |
| 7 | `FunnelInput` דוחה **ישירות במודל** כל אחד מחמשת סוגי הקלט השגוי |
| 7א | **מדיניות המודלים** (ד.0ב): `FunnelInput` דוחה `"1"`, `True`, `1.0` ושדה עודף · **כל שדה `StrictInt`** — `rank` · `bootstrap_iterations` · `ad_budget` · `count` · `sample_size` · `stage_order` · `from_leads` · `to_leads` · `population_n` · `calls` · `n` · `n_records` · **ואיבר ה-`int` בתוך `loc`** — דוחה `True` ו-`1.0` · שדות `StrictBool` דוחים `1`, `0`, `"true"`, `"yes"` · כל מודלי החוזה דוחים `inf`/`nan` |
| 7ב | **`required` ו-`additionalProperties`:** לכל סכמה — קבוצת `required` **מדויקת ומלאה**, הכוללת גם שדות nullable · `additionalProperties: false` בכל מודל · ⛔ אין `default` בשום שדה חוזה · שדה `detail` של `HTTPValidationError` עם `minItems: 1` |
| 8א | כללי OOD פר-משפחה בסכמה: השדות הנכונים nullable, ו-`metrics`/`interval_details`/פרטי המודל **אינם** nullable |
| 8ב | ששת האינווריאנטים של ד.8 נאכפים ב-`model_validator` ונדחים באינסטנציאציה ישירה: תחום-אימון שקרי עם חיזוי מספרי · תחום-אימון שקרי בלי `OODWarning` · **תחום-אימון אמיתי עם `OODWarning`** · תחום-אימון אמיתי עם חיזוי `null` · `evidence_level="low"` בלי `UnobservedBudgetWarning` · `evidence_level=null` עם `UnobservedBudgetWarning`. **בנוסף ארבעת האינווריאנטים של ד.8ב** על `BudgetSimulation`: `strategy_id` בדיוק ארבעת הנעולים · `rank` ייחודי ומכסה 1–4 · המערך מסודר לפי `rank` · `allocations` **תואמים למזהה** לפי `STRATEGY_ALLOCATIONS`. **ובנוסף 12 האינווריאנטים של ד.8ג** (11–22): סדר גבולות ב-P2 וב-P6 · `propensity_band` מול `event_probability`/`base_rate` · `evidence_level` של P6 מול `min(sample_size)` · תקינות `OODWarning` כולל `feature` נעול · חמשת זוגות `stage_order`/`stage` · `to_leads ≤ from_leads` · שרשור `to_leads[i] == from_leads[i+1]` · `drop_rate` null iff `from_leads=0` ואחרת `≈1−to/from` בסובלנות `1e-9` · ייחודיות `calls` וסכום `n` מול `population_n` · זוג `tier_order`/`budget_tier` חוקי · בלי כפילות זוגות ב-`tiers` |
| 8ג | **`Literal` מספרי/בוליאני נאכף ב-`before`-validator** (ד.0ב): `in_training_domain` דוחה `1` ו-`1.0` · `total_budget` דוחה `50000.0` ו-`True` · `tier_order` דוחה `True` ו-`1.0` · `bootstrap_percentiles` דוחה `["2.5","97.5"]` ואת הסדר ההפוך, ומקבל `[2.5, 97.5]` |
| 9 | `MODEL_INPUT_FEATURES[task]` == `meta.json.feature_columns` **בסדר מלא**, לארבע המשימות — 13/13/13/14 |
| 10 | מפתחות ה-CV וה-Holdout הנדרשים לכל ארבע המשימות קיימים ב-`metrics.json[task][meta.json.algo]` — תחת האלגוריתם הזוכה |
| 11 | `STRATEGY_ALLOCATIONS`: מזהים ורמות מול `P6_simulation.json` · `count` והרכב מול `expected` עצמאי מ-`IA.md` §6 · סכום 50,000 לכל אסטרטגיה |
| 12 | סכמות הכשל החלקי (union פר-חלק) והמערך הריק של `budget-tiers` נעולות |
| 13 | OpenAPI מצהיר `components.securitySchemes.BearerAuth` ו-`security` **לששת הנתיבים**; תגובות `401`/`403`/`500`/`503` **לששת הנתיבים**, ו-`422` **לשלושת נתיבי ה-`POST` בלבד** — ⛔ בדיקה שה-`GET` **אינם** נושאים `422` (ד.0) |

⛔ **HTTP אמיתי, Auth בפועל, טעינת מודלים, Supabase ואגרגציות — פאזה 9.**
בפאזה 8 נבדק רק שהן **מוצהרות** ב-OpenAPI ושמודלי הבקשה דוחים קלט שגוי.

---

## י. מה פאזה 8 אינה כוללת

⛔ מימוש endpoint · טעינת `joblib` או `metrics.json` בזמן ריצה · חיזוי ·
זיהוי OOD בפועל · יצירת `warnings` בפועל · קריאת Supabase · עימוד ·
אגרגציה · JWT · שינוי `app/main.py` או `app/auth.py` · אימון מחדש · שינוי
ארטיפקטים · עיצוב חזותי (פאזה 10) · דשבורד (פאזה 11).

---

## יא. סיכונים ובלמים

| סיכון | בלם |
|---|---|
| ארטיפקט נעול שאיש אינו אוכף מולו אחר כך ⇒ נעילה דקורטיבית | פאזה 9 **יורשת** את בדיקת ה-drift ומפנה אותה ל-`app.main.app` האמיתי ב-projection מנורמל; `docs/api/openapi.json` הופך לקריטריון קבלה של פאזה 9 |
| רישום routes באפליקציה החיה היה עולה ל-Render | D1 — אפליקציה מבודדת בתוך הסקריפט בלבד |
| הצהרת `security` בחוזה שלא תואמת את האפליקציה החיה ⇒ בדיקה 13 עוברת בפאזה 8 ונכשלת בפאזה 9 | D13 — חובת פאזה 9 מוצהרת במפורש, לא נגזרת |
| חישוב מחדש של `top_two_overlap` היה יוצר מקור אמת שני, שעלול לסטות מהתוצר הקפוא של פאזה 6 | D9 — קריאה מהערך השמור בלבד. ⚠ אין זו הפרת S9, שנוגעת ל-Holdout בלבד |
| חוזה ה-OOD אינו בר-אכיפה ב-JSON Schema ⇒ צירופים סותרים היו עוברים | ד.8 — שישה אינווריאנטים ב-`model_validator`, שני ביקונדיציונלים סימטריים, נבדקים באינסטנציאציה ישירה (קריטריון 8ב) |
| שינוי `FEATURES` היה שובר את בדיקות פאזה 5 | ו.1 — העברה, לא שינוי |
| פרסור `strategy_id` להסקת `count` | D8 + ו.2 — `STRATEGY_ALLOCATIONS` כמקור יחיד, parity מפוצל |
| ייחוס מגבלת הכיול ל-`PHASE6.md` — הניסוח אינו שם | D6 — ייחוס ל-`P3_holdout.calibration_curve` ולהכרעת פאזה 7 |
| עריכת `codex-history.md` בעדכון `POST→GET` | D10 — ארכיון חתום, אינו נגוע |
| הצהרת `422` ידנית על נתיבי `GET` ⇒ **drift מובטח** מול פאזה 9 | ד.0 — `422` לשלושת ה-`POST` בלבד, ובדיקה מפורשת ש-`GET` אינם נושאים אותו (קריטריון 13) |
| `strategy_id` תקין עם `allocations` של אסטרטגיה אחרת | ד.8ב כלל 10 |
| ברירות המחדל של Pydantic מקבלות `True` כ-`int` ושדות עודפים | ד.0ב — `strict` ל-`int`, `extra="forbid"`, `allow_inf_nan=False` (קריטריון 7א) |
| העברת `model_feature_columns` בלי `DROPPED_COLLINEAR` ⇒ שוברת את הפונקציה ואת `tests/test_train.py:269` | ו.1 — שניהם מועברים, ו-`train.py` מייצא-מחדש |
| אימוץ מבנה 422 של FastAPI ⇒ חוזה שמשתנה בין גרסאות וחושף `input` | ד.7 — חוזה FunnelIQ מצומצם + handler מנרמל בפאזה 9 |
| `LtvPrediction` עם `lower_bound > point_estimate` | ד.8ג **כלל 11** — `lower ≤ point ≤ upper` |
| `StrategyResult` עם `lower_bound > upper_bound` | ד.8ג **כלל 12** — `lower ≤ upper` בלבד; ⛔ `point` **אינו** נדרש בתוך הטווח |
| שדה nullable שנשמט במקום להיות `null` ⇒ הלקוח אינו מבחין בין "אין חיזוי" ל"לא הוחזר" | ד.0ב — כל שדה `required`, בלי `default`; `\| null` מתיר ערך ולא השמטה |
| `ConfigDict(strict=True)` על מודל מעורב מחיל strict גם על `float` | ד.0ב — `StrictInt`/`StrictBool` פר-שדה; ברמת המודל רק ב-`FunnelInput` |
| `OODWarning.feature` כ-`str` חופשי ⇒ אזהרה על שדה שאינו פיצ'ר קלט | ד.7 — `Literal` מ-13 שמות `MODEL_INPUT_FEATURES` |

---

## יב. סבבי הביקורת ומעמד המסמך

התהליך התנהל בשני שלבים נפרדים, 06.09.2026: **חמישה סבבי אפיון** שסגרו
את D1–D13, ולאחריהם **12 סבבי ביקורת מסמכים** (להלן).

### סבבי האפיון

| סבב | תוצאה |
|---|---|
| 1 | טיוטת D1–D12. Codex תיקן שמונה מהן |
| 2 | שתי טענות עובדתיות של Codex אומתו בהרצה **והפריכו את קלוד**: `top_two_overlap` שמור ב-`metrics.json` (קלוד בדק רק את `P6_simulation.json` והסיק "לא קיים"); `FEATURES` אינה 13 השדות |
| 3 | תשע הערות התקבלו. אימות הוביל לממצא שהחליף את המנגנון: `model_feature_columns()` ו-`STRATEGY_ALLOCATIONS` **כבר קיימים** ב-`train.py` ⇒ העברה, לא הוספה. ייחוס מגבלת הכיול ל-`PHASE6.md` הופרך |
| 4 | שני תיקונים: `interval_details` הועבר לתת-מודל של `LtvPrediction` בלבד (`RegressionMetrics` משותף ל-P6, שאין לו כיסוי נמדד) · `accuracy` ו-`n_holdout` הוסרו |
| 5 | שלושה פערים שקלוד העלה באימות — כולם אושרו: **D13** (`app/auth.py` אינו security scheme) · צמצום `POST→GET` לשלושה מופעים (ROADMAP אינו מכיל את המחרוזת; הארכיון אינו נגוע) · `evidence_level` אורתוגונלי ל-OOD |

**שגיאות של קלוד שנתפסו ותוקנו:** הסקת "אין `top_two_overlap`" מבדיקה
חלקית · בדיקת parity שהייתה נכשלת מול `FEATURES` · ייחוס שגוי של מגבלת
הכיול · `interval_details` בתוך בלוק משותף · שדות מדדים מעבר לכלל "רק מה
שהמסך דורש" שקלוד עצמו ניסח · D11 שסתר את D12 (503 על אי-סגירות היה מפיל
גם את `stages` התקין) · הצעת `not_established` במקום `null`, שהייתה יושבת
באותו מרחב ערכים כמו `high|medium|low` ומזמינה רינדור כתווית.

**מעמד:**
✅ **הכרעות D1–D13 אושרו** בחמישה סבבי אפיון (06.09.2026).
⚠ **אישור המסמכים מסבב 3 בוטל ונפתח מחדש** — ר' סבב 4 להלן.
✅ **אישור Codex למסמכים ניתן בתום סבב 11** (06.09.2026), עם אימות עצמאי:
307/307 בדיקות בסיס · `git diff --check` נקי · `PHASE8.md` נבדק בנפרד
כקובץ לא-עקוב.

⚠ **האישור נפתח מחדש בסבב 12** — קריאה עצמאית של קלוד את המסמך במלואו
מצאה ליקוי **חוסם** (ממצא 36: טבלאות הטיפוסים סתרו את ד.0ב) ועוד ארבעה.

✅ **Codex השלים ביקורת חוזרת ואישר את המסמכים בתום סבב 12** (06.09.2026),
**ללא ממצאים נוספים**. אומת: חמשת התיקונים הוחלו נכון, כולל
`ValidationErrorItem.loc` · 307/307 בדיקות בסיס · `node --check` על סקריפט
ה-ROADMAP · `git diff --check` ובדיקת ה-whitespace נקיות.

**ספירות נוכחיות:** 8 checkpoints · 19 קבוצות בדיקה · 12 אינווריאנטים
בד.8ג · **12 סבבי ביקורת מסמכים**.

✅ **המשתמש אישר במפורש את תכנון פאזה 8** (06.09.2026). `planning_status`
עודכן ל-`approved_for_execution`.
⚠ **תצלום היסטורי — רגע אישור התכנון (06.09.2026), לפני הוראת ביצוע:**
אישור תכנון אינו הוראת ביצוע. ⛔ אין לפתוח ענף, אין commit ואין לכתוב
תוצרי קוד (`app/schemas.py`, `scripts/export_openapi.py`,
`docs/api/openapi.json`, `tests/test_api_contract.py`) עד להוראת ביצוע
נפרדת ומפורשת של המשתמש. באותו רגע: `planning_status: approved_for_execution` ·
`execution_status: not_started`.

✅ **מעמד נוכחי (06.09.2026, לאחר הוראת ביצוע נפרדת):** הביצוע הושלם
במלואו — שמונת ה-checkpoints, כולל ביקורת Codex (שני סבבים על
`tests/test_api_contract.py` בלבד, ללא ממצא בסכמות עצמן) וסריקת secrets
על היסטוריית הענף, שניהם עברו נקי. `PR #20` (`main ← feat/api-contract`)
נפתח לאחר אישור מפורש, ומוזג ל-`main` לאחר אישור מפורש נפרד נוסף —
merge commit `5e93bf7`. `pytest -q` ישירות על `main`: 420/420.
`execution_status: done`.

### סבבי ביקורת המסמכים

**סבב 1** (06.09.2026) העלה עשרה ממצאים, כולם התקבלו ותוקנו:
ייחוס אישור Codex למסמכים שטרם נבדקו · "שמונת מפתחות ה-CV" (שבעה שמות
מובחנים — הוסר המספר) · הטענה ש-SPEC נועל את רמת הקינון (הוא נועל שמות
בלבד) · נעילת 15 רכיבי `components.schemas` (המספר תלוי בייצוא Pydantic של
unions ו-generics) · חוזה OOD שלא נאכף ⇒ נוסף ד.8 עם האינווריאנטים ·
ייחוס שגוי של איסור חישוב `top_two_overlap` ל-S9 (S9 נוגעת ל-Holdout
בלבד) · `~512MB RSS` שהוא מגבלת פריסה ולא מדידת import · הבטחת `meta.json`
זהה בייט-לבייט, שפאזה 8 אינה יכולה לאמת · נימוק `warnings` שטען לפרסור
טקסט בפאזה 9 · ו"שארית מיושנת" כתיאור ל-`POST`.

⚠ **שני חידודים שהוספתי מעבר לניסוח הביקורת, ולא יישמתי בשתיקה:**

1. **מנגנון האכיפה של ד.8.** JSON Schema שנפלט מ-Pydantic אינו מבטא תלות
   מותנית בין שדות; לכן האינווריאנטים יושבים ב-`model_validator` ונבדקים
   באינסטנציאציה ישירה, ⛔ **לא** כאילוץ בארטיפקט ה-OpenAPI. בלי אמירה זו
   פאזה 9 הייתה מחפשת אותם ב-JSON.
2. **מקור המתודה `POST`.** אומת ש-`PHASE7.md` **אינו מכיל הכרעת מתודה
   כלל** — היא נכתבה ב-`SPEC.md:289` ונישאה ל-`IA.md`. לכן זו לא "החלטה
   מפורשת של פאזה 7" ולא "שארית", אלא מתודה שמעולם לא נדונה, ופאזה 8
   מכריעה בה לראשונה.

**סבב 2** (06.09.2026) העלה ארבעה ממצאים, כולם התקבלו ותוקנו: הפניה
ל-`D13ב` שאינו קיים (הוחלפה ב-`D2/D5`) · חוסר בכיוון ההפוך של ד.8 —
`in_training_domain=true` עם `OODWarning` הוא צירוף סותר, ולכן נוספה השורה
השלישית והמניין עלה לשישה · שלוש שאריות ברשומת ROADMAP ("15 רכיבי משנה",
"13 קריטריוני קבלה", ונימוק S9) · ו"ה-API **אינו יכול** לייבא מ-`train.py`",
בעוד טכנית הוא יכול וזו החלטת תלות ומשאבים.

⚠ **חידוד שלישי שהוספתי מעבר לניסוח הביקורת:** ד.8 מציג כעת את המבנה כ**שני
ביקונדיציונלים סימטריים** (`in_training_domain=false` ⟺ `OODWarning`;
`evidence_level="low"` ⟺ `UnobservedBudgetWarning`) עם אמירה מפורשת ששניהם
**בלתי תלויים זה בזה**. בלי האמירה הזו ששת האינווריאנטים ניתנים לקריאה
כאילו שני הקשרים מצומדים — וזה סותר את D5.

**סבב 3** (06.09.2026) — Codex דיווח "אין ממצאים" ואישר את שני המסמכים.
⚠ **האישור הזה בוטל בסבב 4.**

**סבב 4** (06.09.2026) — **ביקורת עצמאית של קלוד על המסמכים**, ביוזמת
המשתמש, שהזכיר שאין לקבל דיווחי Codex אוטומטית. הסריקה מצאה **עשרה
ממצאים שסבב 3 לא העלה**, ובעקבותיה **האישור מסבב 3 בוטל**. Codex אימת את
כולם, קיבל תשעה כלשונם, החליף את המנגנון באחד, והוסיף שניים משלו:

| # | ממצא | חומרה |
|---|---|---|
| 1 | ששת הנתיבים אינם מנויים באף מקום; חסר מיפוי endpoint→משימה→בקשה→תגובה | חוסם |
| 2 | `calibration_status`/`calibration_method` כ-`str` חופשי במקום `Literal` | חוסם |
| 3 | `warnings: Warning[]` — טיפוס לא מוגדר, והשם מצל על builtin של Python | חוסם |
| 4 | `StrategyResult.warnings` שדה מת מבנית | בינוני |
| 5 | `Available` מול `AvailablePart` — שני שמות לרכיב אחד | בינוני |
| 6 | רשימת "השדות הנוספים" השמיטה את כל שדות משפחות ה-insights | בינוני |
| 7 | קריטריון 5 אינו ניתן לתרגום לבדיקה דטרמיניסטית | חוסם |
| 8 | ייחוס מגבלת הכיול ל-"שורות D1/D2" — היא ב-D1 בלבד | קל |
| 9 | הפניה משובשת: `(אומת, ב§ 13)` | קל |
| 10 | לפריט `distribution` אין מודל בעל שם | קל |
| 11 | *(Codex)* סכמות משנה מונות שמות בלי לנעול טיפוסים ומגבלות | חוסם |
| 12 | *(Codex)* `SPEC.md:464` דורש אזהרה ב-`uncalibrated` — מקורה לא מופה | בינוני |

⚠ **ממצא 4 — Codex החליף את המנגנון שהצעתי, ובצדק.** הצעתי לתעד את השדה
כמת; `IA.md:375` מסמן את שדה 11 כנדרש **גם ב-P6**, ולכן הסרה או הנמכה
אינה אפשרית. ההכרעה: `max_length=0` — אילוץ נאכף ובר-בדיקה במקום הערת
תיעוד. אומת: `IA.md:375` אכן `✅` בעמודת P6.

⚠ **ממצא 12 — אומת:** `SPEC.md:463-464` דורש *"`uncalibrated` + אזהרה"*,
ו-`SPEC.md:470` מגדיר `calibrated`/`uncalibrated` כ-design tokens. ההכרעה:
האזהרה **מופקת בלקוח מהסטטוס** ואינה נכנסת ל-`warnings[]`, שהוא union סגור
של אזהרות תמיכת-קלט. ⛔ אין להמציא `warning code` שלישי. זהו אותו דפוס של
מגבלת הכיול ב-D6.

**סבב 5** (06.09.2026) — 12 התיקונים אומתו כמיושמים, ושלושת החידודים של
קלוד אושרו. נמצאו **ארבעה פערים חדשים**, כולם התקבלו ותוקנו:

| # | ממצא | תיקון |
|---|---|---|
| 13 | ה.1 טענה ל"כל שדה בכל סכמה" אך חסרה `FunnelInput`, השתמשה ב-wildcards (`metrics.cv.*`) ושיטחה את שני טיפוסי האזהרה יחד | ה.1 נכתבה מחדש בנתיבי JSON מפורשים בלבד |
| 14 | `422` הוצהר על ששת הנתיבים | ⛔ שלושת ה-`POST` בלבד |
| 15 | `strategies` לא ננעל לאורך 4; `rank ge=1 le=4` אינו מונע כפילות או סדר שגוי | `min_length=4, max_length=4` + **ד.8ב** |
| 16 | `uncalibrated` תואר כ"מצב לגיטימי של הארטיפקט" | אינו נגיש — `train.py:2507` |

⚠ **אימות עצמאי חידד את ממצא 14 מעבר לניסוח הביקורת.** הנימוק שניתן —
"ל-`GET` אין קלט שניתן להפר בו ולידציה" — נכון בתוצאה אך לא בכלל. הרצתי
אפליקציית בדיקה בסביבת הפרויקט:

| אופרציה | `responses` | `security` |
|---|---|---|
| `POST` עם גוף + `HTTPBearer` | `['200','422']` | `[{BearerAuth:[]}]` |
| `GET` בלי גוף + `HTTPBearer` | `['200']` | `[{BearerAuth:[]}]` |
| `GET` בלי גוף, בלי אבטחה | `['200']` | — |

**הכלל המדויק:** FastAPI פולט `422` **אם ורק אם** האופרציה מצהירה פרמטרים
או גוף; dependency של `Security` **אינו נספר**. מכאן גם ש-`GET /api/me`
**נושא היום `422`** (אומת מול `app.main.app.openapi()`) — כי `auth.py`
משתמש בפרמטר `Header` ולא ב-security scheme. **מעבר ל-`HTTPBearer` בפאזה 9
יסיר ממנו את ה-`422`** — תוצאת לוואי של D13 שנרשמה כעת ב-ד.0.

⚠ **ממצא 15 — מיקום שונה מהמוצע.** הביקורת ביקשה לבדוק ייחודיות וסדר
במסגרת קריטריון 11. קריטריון 11 בודק **parity של קבוע מול ארטיפקטים**;
ייחודיות `rank` וסדר המערך הם **אינווריאנטים של מודל התגובה**, ואינם
ניתנים לביטוי ב-JSON Schema. לכן נוסף **ד.8ב** ליד ד.8, והבדיקה נכנסה
ל-8ב. סך קבוצות הבדיקה נשאר **14**.

**סבב 6** (06.09.2026) — ארבעת הפערים אומתו כמתוקנים. **שני ממצאים
נוספים**, שניהם התקבלו:

| # | ממצא | תיקון |
|---|---|---|
| 17 | ד.8ב לא קשר בין `strategy_id` ל-`allocations` — מודל תקין יכול לשאת מזהה של אסטרטגיה אחת והרכב של אחרת | נוסף **כלל 10** |
| 18 | `accept.test` ב-ROADMAP נשאר מאחור — לא הזכיר את מפת ה.1, את ד.8ב, ואת הגבלת ה-`422` | `accept.test` נכתב מחדש |

⚠ ממצא 17 הוא הפער האמיתי שנותר בחוזה P6: כללים 7–9 אימתו את **המזהים**,
את **ייחודיות `rank` וכיסוי `{1,2,3,4}`** ואת **סדר המערך** — האורך נאכף
בנפרד ב-`min_length`/`max_length` ואינו אחד מהם. אף אחד מכל אלה לא נגע
ב**תוכן**. ⛔ הוא **אינו** מכסה את
`sample_size`, שמגיע מ-`P6_simulation.json` וקריאתו ב-`app/schemas.py`
סותרת את D1 — אימותו הוא חובת פאזה 9 המוצהרת בד.8ב.

**סבב 7** (06.09.2026) — שתי אי-דיוקים בספירת הסבבים ובתיאור כללים 7–9;
תוקנו בשני המסמכים.

**סבב 8** (06.09.2026) — **שתי ביקורות עצמאיות מקבילות.** קלוד סרק את
המסמך כקורא חדש ומצא 11 ממצאים; Codex סרק במקביל ומצא 8 **אחרים**.
⚠ אין ממצא זהה בין השתיים, אך הן **חופפות בנושאים** — D1 של קלוד חופף
לבדיקת `route→schema` של Codex, ו-`allocations` חופף למשפחת האינווריאנטים
החסרים.

**שמונת ממצאי Codex — כולם אומתו בהרצה והתקבלו:**

| # | ממצא | תוצאת האימות |
|---|---|---|
| 19 | `DROPPED_COLLINEAR` לא נכלל בהעברה | `train.py:168` מגדיר · `:176` תלויה בו · `tests/test_train.py:269` ניגש אליו |
| 20 | מדיניות Pydantic חסרה | pydantic 2.13.4: `int` מקבל `"1"`→1, **`True`→1**, `1.0`→1; שדות עודפים מתקבלים; `inf` מתקבל |
| 21 | חוזה 422 | גוף בפועל `['input','loc','msg','type']`; סכמה אוטומטית `['ctx','input','loc','msg','type']` |
| 22 | `$ref` וחתימות לכל נתיב | `POST`→`requestBody.required=True`; `GET`→אין `requestBody`/`parameters`; `200` הוא `$ref` ישיר |
| 23 | `bootstrap_percentiles` בלי טיפוס | אומת בד.4 |
| 24 | שמונה אינווריאנטים פנימיים חסרים | ⇒ **ד.8ג** |
| 25 | סתירה מול `PHASE7.md:100` | הארטיפקט שומר `n` בלבד, לא תווית |
| 26 | אין checkpoints; `accept.product` כולל את התכנון | פאזות 0–7 משתמשות ב-`{t,s,u,e}` |

⚠ **שגיאה של קלוד בסבב הזה — הוכרעה נגדו:** קלוד טען שחוזה 422 מצומצם
**ייכשל בוודאות**, כי FastAPI מזריק סכמה בת חמישה שדות. **הטענה הופרכה
בהרצה:** כאשר `HTTPValidationError` מקומי מופנה דרך
`responses={422: {"model": …}}`, FastAPI פולט **רק** את סכמות FunnelIQ,
והסכמה האוטומטית אינה מופיעה כלל. ההכרעה של Codex — חוזה מצומצם ויציב עם
handler מנרמל בפאזה 9 — התקבלה.

⚠ **הסתייגות שנבדקה ולא שוחזרה:** Codex הזהיר ש-`strict` גורף על `float`
עלול להיות קשיח יותר מחוזה JSON. נבדק: `strict` float מקבל `2.5`, `50000`,
`np.float32/64` ו-`np.int64`, ודוחה רק `bool` ומחרוזת. **החשש לא אושש** —
ההכרעה (strict ל-`int` בלבד) יושמה בכל זאת, כי הרווח השולי מ-strict על
float אפסי.

**סבב 9** (06.09.2026) — ארבעה ממצאים, כולם התקבלו:

| # | ממצא | תוצאת האימות |
|---|---|---|
| 27 | כלל `required` מול nullable נוסח שגוי | `x: float \| None` בלי `default` **הוא** `required` — השמטה נדחית. בלי התיקון שדות OOD היו יכולים להיעלם |
| 28 | `StrictIntModel` לא מימש "strict רק ל-`int`" | `ConfigDict(strict=True)` דחה גם `float="2.5"` ⇒ `StrictInt`/`StrictBool` פר-שדה. `bool` lax מקבל `1`,`0`,`"true"`,`"yes"`,`"on"`,`1.0` |
| 29 | ה.1 סתרה את האלגוריתם של עצמה | `strategies[]` במקום `strategies`; `stages`/`calls_to_closed` נעדרו |
| 30 | `OODWarning.feature` כ-`str` חופשי | ננעל ל-`Literal` מ-13 שמות `MODEL_INPUT_FEATURES` |

באותו סבב מוקמו האינווריאנטים לפי המודל **שרואה** אותם, נוספו שלושה
כללים שנגזרים ממבנה `followup_insight`, ו-checkpoints 2–3 אוחדו ל-
checkpoint אטומי.

**סבב 10** (06.09.2026) — שני ממצאים:

| # | ממצא | תוצאת האימות |
|---|---|---|
| 31 | `Literal` מספרי/בוליאני אינו מוגן | `Literal[True]`←`1`,`1.0` · `Literal[50000]`←`50000.0` · `Literal[1,2,3]`←`True`,`1.0`. ⚠ **`strict` אינו פותר** — `Literal` נבדק אחרי ה-coercion ⇒ `before`-validator |
| 32 | ה.1 ערבבה נתיבי שורש עם רשימות component-local | ⇒ `root-resolved closure` לשמונת ה-roots |

⚠ `bootstrap_percentiles` הפך ל-`tuple[Literal[2.5], Literal[97.5]]`,
ו**נשאר lax** — `tuple` תחת `strict` דוחה `[2.5, 97.5]`, כלומר את מה
ש-JSON שולח.

**סבב 12** (06.09.2026) — **קריאה עצמאית של קלוד את המסמך במלואו**, ביוזמת
המשתמש. ארבעה ליקויים, אחד מהם **חוסם**; Codex אימת את כולם והוסיף חידוד:

| # | ממצא | חומרה |
|---|---|---|
| 36 | **טבלאות הטיפוסים סותרות את ד.0ב** — 15 שדות כתובים `int`/`bool` חשופים ואפס `StrictInt`/`StrictBool`, בעוד ד.0ב מחייב strict פר-שדה במודל מעורב | **חוסם** |
| 37 | שורה 84 מפנה ל-`IA.md:249-252`; הכלל יושב ב-`IA.md:254` | קל |
| 38 | "8ב מכיל 12 צירופים סותרים" — בפועל **22** (6+4+12), וחלקם כללי תקינות חיוביים ולא צירופים סותרים | קל |
| 39 | `§6.1 להלן` — אין §6.1 במסמך; הכוונה ל-`IA.md` §6.1 | קל |
| 40 | *(Codex)* `ValidationErrorItem.loc` צריך `StrictInt` | בינוני |

⚠ **למה 36 חוסם:** טבלאות ד.2–ד.6 הן **מפרט המימוש** — מהן נכתב
`app/schemas.py`. מי שממש מהן היה מקבל מודל ש-`{"n_records": true}` עובר
בו, בדיוק הכשל השקט שמדיניות ד.0ב נועדה למנוע. המדיניות הייתה נכונה; היא
פשוט לא הגיעה למקום שקוראים ממנו.

⚠ **חידוד 40 אומת בהרצה:** `list[str | int]` מקבל `["body", True]`→`1` ו-
`["body", 1.0]`→`1`; `list[str | StrictInt]` **דוחה את שניהם** ומקבל
`["body", 0]` ו-`["body", "0"]` כרגיל. בלי זה אינדקס בתוך `loc` היה יכול
להגיע כ-`bool`.

**הוחל:** 15 השדות + `loc` הומרו ל-`StrictInt`/`StrictBool` · שתי ההפניות
תוקנו · ניסוח 8ב הוחלף · קריטריון 7א מונה כעת את שדות ה-`StrictInt`
במפורש, כולל איבר ה-`int` בתוך `loc`.

⛔ **לא שונו:** `FunnelInput` נשאר `strict` ברמת המודל · `Literal` מספריים
ובוליאניים נשארים עם `before`-validator · שדות `float` נשארים ללא `strict`.

⚠ **הערה שלא הפכה לממצא:** המסמך מונה 1500+ שורות לחוזה של שישה
endpoints, מהן ~210 היסטוריית ביקורת. הוחלט **לא** להעביר אותה כעת
ל-`codex-review.md`.

**סבב 11** (06.09.2026) — שלוש סתירות תיעודיות, כולן תוקנו:
`Literal[true]` בתחביר Python (חמישה מופעים) → `Literal[True]` ·
ה.1 עדיין כתבה `ErrorDetail.detail` ו-`strategies[].warnings[]` בניגוד
למוסכמת הנתיבים של עצמה, ולא הגדירה דרך אילו מנגנונים הסריקה יורדת ·
ספירת הסבבים נעצרה ב-7 בעוד תועדו 8.

⚠ **תצלום היסטורי — רגע אישור התכנון (06.09.2026), לפני הוראת ביצוע:**
אישור תכנון אינו הוראת ביצוע. באותו רגע `execution_status` היה
`not_started`; לא היה ענף `feat/api-contract`, לא commit ולא PR, עד
להוראה נפרדת ומפורשת.

✅ **מעמד נוכחי (06.09.2026):** הביצוע הושלם, ביקורת Codex וסריקת secrets
עברו ללא ממצא בסכמות, `PR #20` נפתח ומוזג ל-`main` (merge commit
`5e93bf7`) לאחר אישורים מפורשים נפרדים לכל שלב. `execution_status: done`.
