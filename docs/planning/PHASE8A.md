# פאזה 8A — מודל סופר-לקוח (`P4S`) (`feat/super-customer`)

**מעמד:** ההכרעות D1–D21 נסגרו לאחר שישה סבבי אפיון מול Codex (08–09.09.2026),
כחלק מ"תוכנית היישור לבריף" (ר' `docs/planning/codex-review.md`). כל שלב
נבדק בהרצה בסביבת הפרויקט לפני שנכתב — אין הכרעה כאן שמבוססת על הנחה בלתי
מאומתת. **✅ המשתמש אישר במפורש את התכנון והורה על ביצוע (09.09.2026)** ⇒
`planning_status: approved_for_execution`. **checkpoints 1–8 בוצעו ואומתו
בפועל, כולל תיקון provenance (09.09.2026, ר' checkpoint 8 למטה)** —
`execution_status: awaiting_approval` — ענף `feat/super-customer`:
**המימוש מקומט ב-`18bdf4e`; הארטיפקטים והראיות מקומטים ב-`93612c1`.**
checkpoint 11 פתוח וממתין ל-push, פתיחת PR, CI, ביקורת סופית ואישורי מיזוג
וסגירה נפרדים; **אין push, PR או merge** עד הוראה נפרדת ומפורשת נוספת של
המשתמש.
⚠ **אין לטעון שכל 11 ה-checkpoints
הושלמו** — checkpoint 11 עצמו פתוח.

---

## א. מטרת הפאזה

הבריף נועל `Target: referred` (חבילה 4), **ובאותה פסקה** מבקש
*"output a 0–100 likelihood of becoming a super customer"* — **סתירה
פנימית בבריף**, לא הפרה חד-משמעית של דרישה אחת. `docs/planning/PHASE6.md`
בונה ומפריס מודל שעונה על הפרשנות הראשונה (`P4`, הסתברות להפניה). פאזה
זו בונה מודל נוסף (`P4S`) שעונה על השנייה — ציון הסתברותי לתווית
"סופר-לקוח" המשולבת. ⛔ **`P4` הקיים אינו משתנה** — הרחבה שמרנית, לא תיקון.

**הניסוח הקבוע, מחייב בכל תצוגה ותיעוד עתידי (פאזות 9, 11, 13):**

> הציון מעריך את הסיכוי של רשומת לקוח להפוך לסופר-לקוח, בהינתן אותות
> המשפך המוקדמים של הקמפיין. זהו אומדן הסתברותי ולא הבטחה; לקוחות בעלי
> אותות קמפיין זהים יקבלו אותו ציון.

⛔ **ארבע טענות אסורות בכל מקום שהציון מוצג או מתועד:**
1. ודאות מי יהפוך לסופר-לקוח.
2. שהציון מבוסס על מאפייני לקוח אישיים שאינם בקובץ הנתונים.
3. זיהוי ליד לפני רכישה.
4. שחוסר פרסונליזציה ברמת הלקוח הבודד מבטל את היכולת לענות על שאלת הבריף.

⚠ **אוכלוסייה מול נקודת החיזוי (cutoff) — הבחנה שחוזרת לאורך כל המסמך:**
הציון הוא ליחיד **שכבר נמצא** באוכלוסיית `purchased=1`, מחושב מאותות
שנצפו **עד `followup_1`**. ⛔ אינו תקף לליד שטרם רכש, ואינו כלי לזיהוי
לידים.

---

## ב. מצב מאומת — נבדק בהרצה, לא הונח

| # | ממצא | מקור | השפעה |
|---|---|---|---|
| 1 | הגדרת התווית: `purchased==1 AND referred=='Yes' AND upsell==1 AND ltv_months>=34` | `scripts/analysis.py:198`, `super_customer_profile()` | **D2** — התווית כבר מוגדרת מראש ב-SPEC; אין להמציא מחדש |
| 2 | אוכלוסייה 3,163, חיוביים **529 = 16.72%**; **אפס חסרים** בשלושת רכיבי התווית ובארבעת הפיצ'רים בתוך `purchased=1` (`cumulative_profit` נושא 27 חסרים אך מוחרג ממילא) | הרצה ישירה מול `funnel_marketing_data.csv` | **D16** — fail-fast מיותר לגבי חסרים קיימים, אך נדרש כביטוח לעתיד |
| 3 | פיצול `seed=48`, מרובד: **train 2,024/338 · calibration 506/85 · holdout 633/106** | `train_test_split` בדפוס `scripts/train.py:122 split_task()`, נמדד ישירות | **D4, D9** — 85 חיוביים בכיול הם פי 2.5 פחות מ-P3/P4 |
| 4 | `TARGET[task]` משמש כשם עמודה בפועל: `task_population:127`, `split_task:130`, `build_folds:202`, ובנתוני fit בשורות 650/742/801/860 | `scripts/train.py` | **D1** — הוספת `"P4S"` ל-`TARGET` בלי helper תשבור את כל ששת המקומות |
| 5 | seeds תפוסים: `SEEDS` 42–46, **`BOOTSTRAP_SEED=47`**, `ADDITIONAL_SEEDS` 201–203 ⇒ **48 חופשי** | `scripts/train.py:103,1482,1831` | **D3** |
| 6 | `budget_tier` ב-P4: שני המועמדים מקבלים אותו; `encode_budget_tier` שולט **בקידוד בלבד** (passthrough מול one-hot), לא בנוכחות | `train.py:243 build_preprocessing_steps()` | **D7** — P4S חוזרת על אותו דפוס |
| 7 | `cat_features` **שובר `clone()`** של sklearn אם מוגדר בבנאי; מועבר ב-`fit_params` | `train.py:922`, תיעוד ממצא אמפירי מפאזה 6 | **D7** — חובה לרשת את אותו דפוס, אחרת ה-search נכשל באמצע |
| 8 | `LogisticRegression`: **שני ערכים שונים בקוד** — `max_iter=5000` (P3, שורה 762) מול `max_iter=50000` (P4, שורה 982) | `scripts/train.py` | **D7** — P4S צריך לנקוב באיזה משניהם, לא סתם "LogisticRegression" |
| 9 | `OODWarning.feature` נעול ל-13 שמות `MODEL_INPUT_FEATURES["P2"]` | `app/schemas.py` | **D12** — רחב מדי לארבעת פיצ'רי P4S; נדרש טיפוס ייעודי |
| 10 | כשל כיול זורק `RuntimeError` ומונע בניית ארטיפקט deployable | `scripts/train.py:2507` | **D10** — אין fallback ל"לא מכויל" |
| 11 | `ad_budget` ב-P4S train מכיל את **כל 16 הערכים הנצפים** ב-SPEC; `ood_bounds` הנגזרים מ-train זהים לגבולות האוכלוסייה בשלושת הפיצ'רים האחרים | הרצה ישירה, seed 48 | **D13** — `ad_budget` נשאר נעול ב-SPEC (500/20000) ולא נגזר, למרות שהערכים מתלכדים |
| 12 | `EARLY_FUNNEL_FEATURES = [ad_budget, num_leads, leads_answered, followup_1]` כבר קיים כווריאנט `research_only` שחזה `referred`, ROC-AUC `0.7014` | `train.py:1919`, `metrics.json.P4_early_funnel` | **D6** — ⛔ המספר הזה שייך ליעד הישן; אינו ראיה לביצועי P4S |
| 13 | ניסיון לבנות discriminated union עם `OODWarning` ו-`SuperCustomerOODWarning` יחד זורק `TypeError: ... mapped to multiple choices`, כי לשניהם `code="ood_feature_out_of_range"`; `isinstance(w, OODWarning)` כן מחזיר `True` עבור המחלקה היורשת | הרצה ישירה מול `pydantic` המותקן | **D19** — union נפרד הוא הכרח, לא העדפה |

⚠ **תיקוני מהלך שנרשמים כי שינו הכרעה בפועל (לא רק ניסוח):** ההכרעה
המקורית "ה-Holdout של P4S לא יחפוף לאף Holdout אחר" הייתה שגויה
ובלתי-ניתנת למימוש — אוכלוסיית P4S זהה לזו של P2/P3/P4 (§D4). הטענה
"`logistic` נבחר על סמך תוצאת ה-Holdout" הייתה שגיאה מתודולוגית — הבחירה
נעשתה **לפני** פתיחתו, לפי כלל One-SE (§D-ref ל-PHASE6.md:693–695).
הטענה "רוחב טווח = סיכון עסקי" (מפאזה מקבילה) הייתה שגיאה סטטיסטית —
רוחב Bootstrap הוא אי-ודאות באומדן, לא סיכון נמדד.

---

## ג. הכרעות התכנון — D1–D21

### D1 — יעד סינתטי, helper יחיד
`TARGET["P4S"] = "super_customer"` הוא **מזהה לוגי**, ⛔ **אינו עמודת CSV**
(מתועד במפורש בקוד ובתיעוד). כל גישה לערכי יעד עוברת דרך **helper יחיד**:
במשימות הקיימות הוא מחזיר את עמודת היעד עצמה; ב-`"P4S"` הוא מחזיר
`super_customer_label(df)`. כך `_feature_list`, `FEATURES`,
`MODEL_INPUT_FEATURES`, `column_status` וה-metadata נשארים עקביים בלי
ענף מיוחד בכל אחד מהם. `referred`, `upsell`, `ltv_months` מסומנים
`Excluded`/רכיבי-תווית ב-`feature_matrix.md` עבור `P4S`, ⛔ לעולם לא
פיצ'רים.

### D2 — מקור אמת יחיד לתווית
`super_customer_label(df: pd.DataFrame) -> pd.Series` ב-`app/features.py`
— פונקציה טהורה, מיושרת ל-`df.index`, ⛔ **אינה משנה את `df`** בכל צורה
(לא column חדש, לא mutation באתר). `super_customer_profile()` ב-
`scripts/analysis.py` **צורכת אותה**, ⛔ ואינה מחשבת את שלושת התנאים
שוב בנפרד. הקריטריון שנועל את זה: **אין מימוש חישובי שני של הנוסחה
בקוד** — ⛔ לא "אפס מופעי `grep`", כי הנוסחה מופיעה כדין בהערות תיעוד,
בבדיקות ישירות, וב-`target_definition` שהחוזה מחזיר (D14).

### D3 — seed = 48
42–46 תפוסים ב-`SEEDS`, **47 תפוס ב-`BOOTSTRAP_SEED`**, 201–203
ב-`ADDITIONAL_SEEDS`. 48 אומת כחופשי בהרצה נגד הקובץ המלא.

### D4 — זרות פנימית בלבד
`train`, `calibration` ו-`holdout` של P4S **זרים זה לזה**, ואיחודם הוא
**בדיוק** אוכלוסיית P4S (3,163). ⛔ הדרישה המקורית "אי-חפיפה מול
Holdouts של משימות אחרות" הייתה שגויה ובלתי-ניתנת למימוש: אוכלוסיית P4S
היא אותם 3,163 רשומות של P2/P3/P4 (`purchased=1`), וחפיפה ברמת
`source_row_id` היא הכרחית וקיימת כבר היום בין ארבע המשימות הקיימות
(seeds נפרדים 42–45).

### D5 — entry point מבודד
⛔ אין להריץ את הצינור המלא (`python scripts/train.py` בלי דגל) — הוא
פותח מחדש את Holdout של P2/P3/P4/P6, בניגוד ל-S9. ר' D21 למנגנון
המדויק.

### D6 — מקור אמת יחיד לפיצ'רים המוקדמים
`EARLY_FUNNEL_FEATURES` עובר מ-`scripts/train.py:1919` ל-
`app/features.py`; ניסוי `P4_early_funnel` הקיים (`train.py`) מייבא
משם ולא משכפל את הרשימה. ⚠ **קריטריון פרזיטי:**
`metrics.json.P4_early_funnel.mean_roc_auc` חייב להישאר `0.701374698320084`
בייט-לבייט אחרי ההעברה — אם הוא זז, ההעברה שינתה משהו שהיא לא הייתה
אמורה לגעת בו.

### D7 — תצורת האימון, נעולה מראש
**CatBoost:**
`learning_rate=[0.01, 0.05, 0.1, 0.2]` · `depth=[3, 4, 5, 6]` ·
`iterations=[200, 400, 800]` · `n_iter=20` · `cv` על 5 folds ·
`SEARCH_RANDOM_STATE=42` · `thread_count=1` ·
**`model__cat_features` מועבר ב-`fit_params`, ⛔ לעולם לא בבנאי**
(`CatBoostClassifier(cat_features=[...])` שובר `clone()` — ממצא 7 ב-§ב).

**Logistic baseline:** `LogisticRegression(max_iter=50000)` —
**במפורש כמו P4, שורה 982**, ⛔ לא `5000` של P3 (שורה 762) — שני
ערכים שונים קיימים בקוד ובלי לנקוב באיזה מהם מי שיממש עלול להעתיק
את הלא-נכון.

**Dummy:** `DummyClassifier` כ-benchmark בלבד, ⛔ אינו מועמד לפריסה.

**שני המועמדים מקבלים `budget_tier`**, נגזר מ-`ad_budget` **בתוך
ה-Pipeline** (לא שדה קלט חמישי): CatBoost בטיפול קטגוריאלי נייטיב
(passthrough), Logistic ב-one-hot — בדיוק דפוס P4 (`build_preprocessing_steps`).

### D8 — איזון מחלקות: הכרעה סופית, ללא ענף פתוח
שני המודלים מאומנים **ללא `class_weight`**. מדובר באומדן הסתברות
מכויל; stratification (D4), PR-AUC ו-Brier (D9) מספקים את המדידה
הדרושה. ⛔ אין הכרעה מותנית ("רק אם ה-CV מצדיק") — היא הייתה משאירה
החלטה בלי כלל וניסוי מוגדרים.

### D9 — מדדים ודיווח
ראשי לבחירת מנצח: **ROC-AUC**. משניים: PR-AUC, Brier.
Accuracy/Precision/Recall/F1 בסף **קבוע 0.5**, **לדיווח בלבד** —
⛔ אינם קריטריון בחירה.

⚠ **צפי מוצהר מראש:** בשיעור בסיס 16.72%, סף 0.5 צפוי לייצר מעט מאוד
תחזיות חיוביות, ולכן Recall ו-F1 עלולים להיות נמוכים מאוד או קרובים
לאפס. **זו תוצאה צפויה, לא פגם בבחירת המודל** — ⛔ אין להזיז את הסף
בדיעבד כתגובה לכך.

**דיווח CV:** mean/std/SE, במנגנון הקיים (`one_se_stats`).
**דיווח Holdout:** point estimate, `n`, ושיעור חיוביים, עם הסתייגות
מפורשת מרעש המדגם (106 חיוביים). ⛔ **אין לייחס SE שחושב על ה-CV
למדד ה-Holdout** — הם נמדדים על אוכלוסיות שונות ואינם אותו מספר.

### D10 — כיול חובה, ללא fallback
`sigmoid` על סט הכיול, כדפוס P3/P4. כשל = **כשל רועש** — ⛔ ללא
ארטיפקט deployable, ⛔ ללא "לא מכויל" כמצב חוקי. חוזה P4S:
`calibration_status: Literal["calibrated"]` בלבד — **הידוק מכוון** מול
P3/P4 (ששם `"uncalibrated"` קיים בסכימה כמצב fallback תיאורטי, אך אינו
נגיש בארטיפקטים הנוכחיים גם שם).

### D11 — הקפאה לפני פתיחה, ופתיחה יחידה
כל ההכרעות (מועמדים, גריד, שובר שוויון, מדיניות כיול, סף 0.5) מוקפאות
**לפני** פתיחת ה-Holdout, מתועדות ב-commit מתוארך. **מדדים, עקומת כיול
ופילוח `budget_tier` מחושבים כולם באותה פתיחה יחידה** (checkpoint 7).
⚠ ה-Holdout **אינו חיצוני ואינו בלתי-נגוע** במובן המלא — הדאטה עבר EDA
מלא בפאזה 5 לפני שהמשימה הזו נולדה; הוא רק לא שימש לבחירת P4S אחרי
ההקפאה.

### D12 — OOD ייעודי
warning ייעודי ל-P4S (ר' D19) שנועל `feature` **לארבעת שדות הקלט
בלבד**, ⛔ לא ל-13 השמות שה-`OODWarning` הקיים מתיר.

### D13 — גבולות OOD ותקציב שלא נצפה
`ood_bounds["ad_budget"]` **נעול ל-500/20000 לפי SPEC**, ⛔ אינו נגזר
מהפיצול — כדפוס P2/P3/P4/P6. גבולות `num_leads`, `leads_answered`,
`followup_1` — **מ-P4S train בלבד**. `observed_ad_budget_values` —
**מ-P4S train בלבד**; בפיצול הנעול (seed 48) נמדדו **כל 16 הערכים**,
כך שבפועל אין הבדל תפעולי מ-500/20000, אך הכלל חייב להישאר זהה
לאחיו למקרה שפיצול עתידי (למשל אם המודל ייבנה מחדש) יראה פחות מהם.

### D14 — הגדרות מפורשות בחוזה
`target_definition` **לצד** `population_definition="purchased=1"` בכל
תגובה. ⛔ אחד בלי השני מטעה — `target_definition` בלי `population_definition`
משתמע שהמודל תקף לכל אוכלוסייה; ההפך גם.

### D15 — עקביות הציון: שתי בדיקות נפרדות ומדידות
א. **דטרמיניזם:** אותה בקשה שוב מחזירה `event_probability` זהה
   ביט-בביט.
ב. **המרה לתצוגה:** `display_score = Math.round(event_probability * 100)`
   — כלל נעול, ממומש בפאזה 11. ⛔ שתי הבדיקות נפרדות — האחת בודקת
   שרת, השנייה בודקת חוזה תצוגה; דרישה "אותו ציון לפני ואחרי ההמרה"
   אינה מדידה כשלעצמה.

### D16 — fail-fast על נתונים חסרים
בדיקה שמוכיחה **אפס חסרים** בשבעת השדות (שלושת רכיבי התווית + ארבעת
הפיצ'רים) **לפני** הפיצול. ⛔ אין imputer ואין מסנן זכאות בפועל היום
(ממצא 2: אין חסרים) — אבל שינוי עתידי בנתוני המקור לא יהפוך `NaN`
לשלילי בשקט דרך `NaN >= 34`.

### D17 — פילוח `budget_tier`, תמיד מלא
מדווח **תמיד** `n`, `base_rate`, `Brier` לכל טייר, גם כשהמדגם קטן.
`ROC-AUC`/`PR-AUC` = **`null` עם סיבה מפורשת** (`"single_class"` או
דומה) כשאין בשכבה שתי מחלקות בפועל.

### D18 — שני baselines נפרדים
⚠ **83.28% הוא שיעור רוב אוכלוסייתי משוער** (`1 - 0.1672`),
⛔ **לא תוצאת Holdout**. מדווח **בנפרד** ה-Dummy שנמדד בפועל על סט
ה-Holdout (יכול לסטות מ-83.28% בגלל גודל המדגם).

### D19 — טיפוס האזהרה, ואיסור נעול
```python
class SuperCustomerOODWarning(OODWarning):
    feature: Literal["ad_budget", "num_leads", "leads_answered", "followup_1"]
```
`SuperCustomerPrediction.warnings` הוא union **נפרד**:
`Annotated[Union[SuperCustomerOODWarning, UnobservedBudgetWarning], Field(discriminator="code")]`.

✅ אומת בהרצה: הצמצום ל-4 שמות תופס, שם מתוך ה-13 המקוריים נדחה,
ו-`isinstance(w, OODWarning) is True` — כלומר האינווריאנטים הקיימים
של ד.8 (`app/schemas.py`) ממשיכים לזהות אזהרת OOD גם דרך המחלקה
היורשת.

⛔ **איסור נעול, אומת בהרצה:** אסור לכלול את `OODWarning` ואת
`SuperCustomerOODWarning` **באותו** discriminated union — שניהם נושאים
`code="ood_feature_out_of_range"`, ופידנטיק זורק
`TypeError: Value 'ood_feature_out_of_range' for discriminator 'code' mapped to multiple choices`.
⛔ `ContractWarning` הקיים (המשותף לחוזה הנעול של פאזה 8) **אינו
מורחב** — P4S מקבל טיפוס warnings משלו.

### D20 — חוזה הנתיב
`POST /api/predict/super-customer`

| שדה | ערך |
|---|---|
| `requestBody` | `EarlyFunnelInput`, `required: true` |
| `200` | `SuperCustomerPrediction` |
| `401`, `403` | `ErrorDetail` |
| `422` | `HTTPValidationError` |
| `500`, `503` | `ErrorDetail` |
| `security` | `[{"BearerAuth": []}]` |
| `operationId` | ייחודי (נגזר משם הפונקציה) |

⚠ **500 ו-503 נדרשים במפורש** — נתיב עם ארבעה קודים בלבד (ללא 500/503)
היה סותר גם את שלושת ה-POST הקיימים בחוזה הנעול של פאזה 8 וגם את
שלושת ה-handlers של D7 בתכנון פאזה 9, שמייצרים אותם בפועל לכל נתיב
עסקי. הנתיב צורך את **אותו** `ERROR_RESPONSES`/`ERROR_RESPONSES_NO_422`
מ-`app/api_contract.py` (מקור יחיד — ר' תכנון פאזה 9, D7/D8).

⛔ **ששת הנתיבים הקיימים — deep-equality מלא ב-root-resolved
projection**, ⛔ לא זהות בתים: הוספת נתיב שביעי משנה את
`docs/api/openapi.json` בהכרח. ⛔ **פאזה 8 אינה נפתחת מחדש** —
PHASE8A מחזיקה גרסת חוזה **אדיטיבית** חדשה, לא תיקון של הקיימת.

`EarlyFunnelInput`: ארבעה `StrictInt` `ge=0`, `extra="forbid"`,
`strict=True`; אינווריאנטים: `num_leads>0` · `leads_answered<=num_leads`
· `followup_1<=leads_answered`.

`SuperCustomerPrediction`: שדות `PropensityPrediction` (`event_probability`,
`base_rate`, `propensity_band`, `evidence_level`, `in_training_domain`,
`model_version`, `model_algorithm`, `metrics`), **פרט ל**-`calibration_status`
שהוא `Literal["calibrated"]` בלבד (D10), **בתוספת** `target_definition`
ו-`population_definition` (D14), עם `warnings` הייעודי (D19).

### D21 — מסלול הרצה מבודד
```
python scripts/train.py --run-p4s
```
מריץ **אך ורק** את checkpoints של P4S: פותח **רק** את Holdout של P4S,
**פעם אחת**, ומוסיף **רק** תוצרי P4S למערכת הקבצים ול-`metrics.json`.
⛔ **אינו עובר למסלול `main`** של הסקריפט (הצינור המלא של P2/P3/P4/P6)
ו⛔ **אינו מפעיל שום פונקציית אימון או Holdout שלהם.**

⚠ **הערת מימוש שחייבת להיאמר מראש, לא להתגלות:** בדפוס
`--build-artifacts` הקיים (`scripts/train.py`, checkpoint 15 של פאזה 6),
`SystemExit(0)` מגיע **לפני** קוד הצינור המלא, אבל **אחרי** ה-self-reimport
שמתקן את `__module__` של `_add_budget_tier`/`_Winsorizer` (נדרש כדי
שהארטיפקט הנשמר יהיה ניתן ל-pickle בתהליך אחר — בדיוק המלכודת
שפאזה 6 כבר נפלה בה ותיעדה ב-D10 שלה). `--run-p4s` חייב לשמור על אותו
סדר: self-reimport תמיד רץ, ואז הענף הרלוונטי (`--build-artifacts`,
`--run-p4s`, או המסלול הרגיל) מסתעף.

---

## ד. מפת אינטגרציה — הוכחת אפס שינוי ב-P2/P3/P4/P6

⚠ **"אפס שינוי" פירושו אפס שינוי בהתנהגות ובתוצרים, ⛔ לא אפס שינוי
בקוד.** מותר לשנות מסלול קוד משותף לצורך ה-target helper (D1) והעברת
`EARLY_FUNNEL_FEATURES` (D6) — זה בדיוק מה שהופך אותם ל"מקור אמת יחיד"
ולא לשני מקורות.

| רכיב | מיקום | השינוי הנדרש | הוכחת אי-פגיעה |
|---|---|---|---|
| `TARGET` | `app/features.py` | ⛔ **לא** מקבל מפתח `"P4S"` שמצביע על עמודת CSV | ערכי ארבע המשימות הקיימות ללא שינוי |
| `super_customer_label()` | `app/features.py` | **חדש** | פונקציה טהורה חדשה; ⛔ אף משימה קיימת אינה קוראת לה |
| `EXCLUDED`, `FEATURES`, `MODEL_INPUT_FEATURES` | `app/features.py` | מפתח `"P4S"` נוסף | ערכי ארבע המשימות הקיימות ללא שינוי (`test_features.py`) |
| `EARLY_FUNNEL_FEATURES` | `train.py:1919` → `app/features.py` | **העברה** + re-export ב-`train.py` | `P4_early_funnel.mean_roc_auc` = `0.701374698320084` בייט-לבייט |
| `SEEDS` | `train.py:103` | `"P4S": 48` נוסף | 42–46 ללא שינוי |
| `STRATIFIED_TASKS` | `train.py:107` | `{"P3", "P4"} → {"P3", "P4", "P4S"}` | — |
| `task_population`, `split_task`, `build_folds` | `train.py` | ענף ל-`"P4S"` דרך ה-helper (D1) | פיצולי ארבע המשימות זהים לפי `source_row_id` |
| `SCORING`, `PRIMARY_METRIC` | `train.py:~492` | `"P4S": "roc_auc"` | ערכים קיימים ללא שינוי |
| `encode_referred_target` | `train.py:267` | ⛔ ללא שינוי — ייעודי ל-P4 | — |
| מבני מועמדים/כיול/Holdout | `train.py` | מסלול P4S נפרד (D21) | ⛔ אף פונקציית Holdout ישנה אינה נקראת |
| artifact/meta builders, `fit_sources` | `train.py` | `"P4S"` נוסף | **SHA-256 של ארבעת ה-`*.joblib` וארבעת ה-`*.meta.json` הקיימים — זהה** |
| orchestrator (`__main__`) | `train.py:~2630` | `--run-p4s` נוסף (D21) | ⛔ אף תת-עץ קיים ב-`metrics.json` אינו משתנה |
| `app/schemas.py` | — | שני מודלים חדשים + `SuperCustomerOODWarning` | deep-equality של projection ששת הנתיבים הקיימים |

---

## ה. checkpoints — סדר מחייב

| # | פעולה | ראיה |
|---|---|---|
| 1 | ענף `feat/super-customer` מ-`main` מסונכרן | ✅ בוצע 09.09.2026 — ענף נפתח מ-`main` (HEAD = merge PR #21) |
| 2 | `app/features.py`: `super_customer_label()`, target helper (D1), העברת `EARLY_FUNNEL_FEATURES` (D6), מפתחות `"P4S"` ב-`TARGET`/`EXCLUDED`/`FEATURES`/`MODEL_INPUT_FEATURES` | ✅ בוצע 09.09.2026 — אומת ידנית: `FEATURES["P4S"]`/`MODEL_INPUT_FEATURES["P4S"]` = ארבעת השדות; `super_customer_profile()` (analysis.py) עודכן לצרוך את `super_customer_label` וממשיך להחזיר 529/3163/33.61%/990.7 (ללא שינוי); `pytest tests/test_features.py` — ר' checkpoint 11 |
| 3 | `scripts/train.py`: אוכלוסייה, `SEEDS["P4S"]=48`, `STRATIFIED_TASKS += "P4S"`, fail-fast חסרים (D16), `--run-p4s` (D21) | ✅ בוצע 09.09.2026 — הפיצול מדד בפועל: population=3,163, train=2,024 (338 חיוביים), calibration=506 (85), holdout=633 (106) — זהה למספרים הנעולים במסמך זה; P2/P3/P4/P6 נמדדו מחדש עם אותו `split_task` המתוקן ונותנים בדיוק train=2,024/cal=506/holdout=633 (P2/P3/P4) ו-train=2,776/holdout=695 (P6) — ⛔ אפס שינוי |
| 4 | **הקפאת ההכרעות** — מועמדים, grid, שובר שוויון, מדיניות כיול, סף 0.5 | ✅ תועד 09.09.2026 בעריכת קובץ פשוטה (⚠ **סטייה מוצהרת**: ההוראה אוסרת commit; "commit מתוארך" ב-PHASE8A.md המקורי מוחלף כאן בעריכת מסמך מתוארכת, ללא commit בפועל) — המועמדים (CatBoost + Dummy/Logistic baselines, D7), ה-grid (D7, זהה ל-P4), שובר השוויון (`select_winner` הקיים, ללא שינוי), מדיניות הכיול (sigmoid חובה, D10) והסף (0.5, D9) כולם כבר נעולים בסעיפי D7–D10 לעיל; אין שינוי בהם מרגע אישור התכנון. נקודת ההקפאה בפועל: **לפני** הרצת `train_p4s()` הראשונה, 09.09.2026 |
| 5 | CV + בחירה — ⛔ **בלי Holdout** | ✅ בוצע 09.09.2026 — `catboost` (candidate, mean ROC-AUC=0.7835) ו-`logistic` (baseline, mean ROC-AUC=0.7924) הורצו; `eligible=["logistic"]` (catboost מחוץ ל-One-SE של logistic), **winner=logistic** — `metrics.json.P4S`, `metrics.json.P4S_selection` |
| 6 | כיול `sigmoid` על סט הכיול | ✅ בוצע 09.09.2026 — `calibration_status=calibrated`, `calibration_method=sigmoid` — `metrics.json.P4S_calibration`; ⚠ ר' סיכון R1 (85 חיוביים בסט הכיול) |
| 7 | **פתיחת Holdout יחידה** — מדדים, עקומת כיול, פילוח `budget_tier`, **הכל כאן** | ✅ בוצע 09.09.2026 — n=633, ROC-AUC=0.8187, PR-AUC=0.3779, Brier=0.1126, log_loss=0.3277; Accuracy/Precision/Recall/F1 בסף 0.5 = 0.8325/0/0/0 (**צפוי, ר' R8** — 106/633=16.7% חיוביים); Dummy-on-Holdout: accuracy=0.8325, brier=0.1675; פילוח `budget_tier`: Mid (n=328) ROC-AUC=0.5696 PR-AUC=0.3779, Low/High (n=116/189) — AUC=`null` (מחלקה יחידה) — `metrics.json.P4S_holdout` |
| 8 | ארטיפקטים, metadata, checksum | ✅ **provenance תוקן ואומת 09.09.2026**: commit `18bdf4e` (קוד+בדיקות+חוזה+תיעוד בלבד, ללא תוצרי אימון) → `git status --short` ריק אומת → `python scripts/train.py --run-p4s` הורץ מחדש מ-`18bdf4e` הנקי → `models/P4S.meta.json.model_version = "P4S-logistic-20260909-18bdf4e"` — ה-SHA המוטבע **תואם בדיוק** ל-HEAD בזמן הבנייה. תוצאות זהות ביט-לביט לריצה הזמנית הקודמת (דטרמיניזם מאומת: ROC-AUC=0.8187050230926212, PR-AUC=0.37789662094554244, Brier=0.11263749662023682, sha256 של ה-`.joblib`=`27b39407…` זהה). `pytest -q`: 448/448. אפס רגרסיה ב-P2/P3/P4/P6 (checksums זהים, אפס מפתחות `metrics.json` ישנים השתנו, רק 4 מפתחות `P4S*` נוספו). |
| 9 | `app/schemas.py`: `EarlyFunnelInput`, `SuperCustomerPrediction`, `SuperCustomerOODWarning` | ✅ בוצע 09.09.2026 — `tests/test_schemas_p4s.py` (8 בדיקות): `isinstance(w, OODWarning)`, דחיית feature זר, `TypeError` על union מעורב, כללי עסק, דחיית `calibration_status="uncalibrated"` |
| 10 | ייצוא `docs/api/openapi.json` מחדש עם שבעה נתיבים | ✅ בוצע 09.09.2026 — `app/api_contract.py` נוצר; `tests/test_api_contract_p4s.py` (5 בדיקות, מול fixture קפוא של הקובץ הישן): ששת הנתיבים/`securitySchemes`/כל סכמת רכיב ישנה — זהים בתים; **ממצא חדש**: `tests/test_api_contract.py`'s `test_group2_exactly_six_business_routes_with_locked_methods` הניח בדיוק 6 נתיבים — עודכן להכיר בנתיב השביעי האדיטיבי (ר' דוח הביקורת) |
| 11 | סגירה | ⏸ **פתוח — נעצר לפני push/PR/מיזוג לפי ההוראה המפורשת**. **המימוש מקומט ב-`18bdf4e`; הארטיפקטים והראיות מקומטים ב-`93612c1`.** `pytest -q`: 448/448 עברו (430 שהיו + 18 חדשות: 8 ב-`test_schemas_p4s.py`, 5 ב-`test_api_contract_p4s.py`, 5 ב-`test_train.py`); אפס רגרסיה ב-P2/P3/P4/P6 (SHA-256 של כל ארבעת ה-`*.joblib`/`*.meta.json` + `P6_simulation.json`/`run_metadata.json` זהים בתים; מפתחות `metrics.json` הישנים ללא שינוי, רק 4 מפתחות `P4S*` נוספו); `git diff --check` נקי (מלבד אזהרת LF/CRLF שגרתית). ⛔ **נותר**: push לענף מרוחק, פתיחת PR, CI, ביקורת Codex סופית, ⚠ אישור מיזוג נפרד, אימות `main`, ⚠ אישור סגירת פאזה נפרד נוסף — כל אחד ממתין להוראה מפורשת משלו |

⚠ `ROADMAP.html` מתעדכן **מיד אחרי כל checkpoint שבוצע ואומת**, לא רק
בסיום. פעולה ידנית מסומנת `done` רק לאחר אישור המשתמש.

---

## ו. קריטריוני קבלה

1. `super_customer_label()` היא המקור המחשובי היחיד לתווית — אין מימוש
   שני שלה בקוד; `super_customer_profile()` צורכת אותה.
2. הפונקציה ⛔ אינה משנה את `df` — נבדק בהשוואת עותק לפני/אחרי הקריאה.
3. רגרסיה על `super_customer_profile()`: **529 / 3,163** ויתר השדות
   (`pct_of_total_profit`, `cac_super_mean` וכו') ללא שינוי.
4. `train`/`calibration`/`holdout` של P4S **זרים**, ואיחודם = אוכלוסיית
   P4S בדיוק (3,163 לפי `source_row_id`).
5. הגדלים המדויקים: **train 2,024 / 338 חיוביים · calibration 506 / 85
   · holdout 633 / 106**.
6. `SEEDS["P4S"] = 48`; ⛔ אינו מתנגש ב-`SEEDS` הקיימים או ב-`BOOTSTRAP_SEED`.
7. **SHA-256 של ארבעת ה-`*.joblib` וארבעת ה-`*.meta.json` הקיימים —
   זהה לפני ואחרי הפאזה כולה.**
8. כל תת-העצים הקיימים ב-`metrics.json` זהים; רק מפתחות `P4S*` נוספים.
9. `metrics.json.P4_early_funnel.mean_roc_auc = 0.701374698320084` —
   ללא שינוי אחרי checkpoint 2.
10. Holdout של P4S נפתח **פעם אחת בלבד**; בדיקת orchestration/tripwire
    (בדפוס D22 של `PHASE6.md`) סופרת קריאות.
11. `calibration_status = "calibrated"` בכל ארטיפקט שנבנה, או כישלון
    רועש (`RuntimeError`) — ⛔ אין ארטיפקט לא-מכויל בפריסה.
12. **שני baselines נפרדים מדווחים:** ~83.28% אוכלוסייתי (D18)
    **ו**-Dummy שנמדד בפועל על ה-Holdout.
13. פילוח `budget_tier` מדווח **תמיד** עם `n`/`base_rate`/`Brier`; AUC
    = `null` + סיבה מפורשת כשאין בשכבה שתי מחלקות.
14. התגובה נושאת `target_definition` **ו**-`population_definition`
    יחד, לעולם לא רק אחד מהם.
15. `SuperCustomerOODWarning` נועל `feature` לארבעה שדות; שם מתוך
    13 השמות הישנים **נדחה** באינסטנציאציה ישירה.
16. **ה-search של CatBoost מסתיים בהצלחה** — `cat_features` הועבר
    ב-`fit_params`, ⛔ לא בבנאי (אחרת `RuntimeError` באמצע ה-search).
17. **שתי בדיקות נפרדות ולא אחת:** D15א (דטרמיניזם `event_probability`)
    ו-D15ב (`Math.round(p*100)` בפאזה 11).
18. **fail-fast חסרים** — הבדיקה נכשלת כשמזריקים `NaN` מלאכותי לאחד
    משבעת השדות (שלושת רכיבי התווית + ארבעת הפיצ'רים).
19. `ood_bounds["ad_budget"] = {min: 500, max: 20000}` (SPEC, קבוע);
    שלושת האחרים נגזרים מ-P4S train.
20. **deep-equality של ה-projection** לששת הנתיבים הקיימים; בדיקת
    mutation על עותק בזיכרון (⛔ לא על הקובץ בדיסק) חייבת להיכשל.
21. `isinstance(w, OODWarning)` מחזיר `True` עבור מופע של
    `SuperCustomerOODWarning` — אינווריאנטי ד.8 הקיימים ממשיכים לזהות
    אזהרת OOD דרך המחלקה היורשת.
22. **בדיקה שמוודאת שאין discriminated union המכיל את `OODWarning`
    ואת `SuperCustomerOODWarning` יחד** — היא עצמה חייבת להיכשל
    ב-`TypeError` (לא לעבור בטעות).
23. הנתיב השביעי מצהיר **200/401/403/422/500/503** ו-`security: BearerAuth`,
    מאותו `ERROR_RESPONSES`/`ERROR_RESPONSES_NO_422` ב-`app/api_contract.py`
    ששלושת נתיבי ה-POST הקיימים משתמשים בו.
24. `--run-p4s` — ⛔ **אפס קריאות** לפונקציות אימון או Holdout של
    P2/P3/P4/P6; נבדק במונה קריאות (mock/spy על הפונקציות הרלוונטיות).

---

## ז. מה הפאזה אינה כוללת

- ⛔ שינוי כלשהו ב-`P4` הקיים (מודל, endpoint, סכמה) — נשאר referral בלבד.
- ⛔ פתיחה מחדש של Holdout כלשהו של P2/P3/P4/P6.
- ⛔ שינוי `docs/api/openapi.json` בששת הנתיבים הקיימים — רק תוספת אדיטיבית.
- ⛔ תצוגת 0–100 בממשק — שכבת תצוגה, פאזה 11.
- ⛔ חיבור הנתיב לאפליקציה החיה (`app/main.py`) ובדיקות HTTP אמיתיות —
  אלה שייכים לתכנון פאזה 9, שנבחן מחדש אחרי פאזה זו.
- ⛔ עדכון `REPORT.md`/`README.md` — פאזה 13.
- ⛔ פתיחת פאזה 6 או עריכת `PHASE6.md` — B38 (למה `logistic` נבחר על
  פני CatBoost בפועל) מתועד שם ומוצג ב-REPORT בלבד.

---

## ח. סיכונים ובלמים

| # | סיכון | בלם |
|---|---|---|
| R1 | **85 חיוביים בלבד בסט הכיול** — פי 2.5 פחות מ-P3/P4; כיול `sigmoid` עלול להיות לא יציב | עקומת כיול **חובה** (D11) · כשל כיול = כשל רועש (D10) · קריטריון 11 |
| R2 | 106 חיוביים ב-Holdout ⇒ PR-AUC, precision ו-recall רועשים | D9 — point estimate + `n` + שיעור חיוביים עם הסתייגות; ⛔ אין SE מושאל מ-CV |
| R3 | ארבעה פיצ'רים בלבד ⇒ הבחנה מוגבלת; AUC צפוי נמוך מ-P3/P4 | מוצהר מראש; הבריף מעדיף מודל כן על מודל מנופח |
| R4 | תווית שהיא צירוף שלושה תנאים קשה לניבוי מכל רכיב בודד | R3 |
| R5 | **הרצה שתפתח בטעות Holdout של משימה ישנה** | D5 + D21 + קריטריונים 7–10, 24 |
| R6 | שכפול נוסחת התווית ⇒ שני מקורות אמת שעלולים לסטות | D2 + קריטריון 1 |
| R7 | התנגשות seed עם `SEEDS` או `BOOTSTRAP_SEED` הקיימים | D3 + קריטריון 6 |
| R8 | Precision/Recall/F1 אפסיים או כמעט-אפסיים בסף 0.5 | D9 — **מוצהר כצפוי מראש**; ⛔ אין להזיז את הסף בדיעבד |
| R9 | בלבול בין P4S ל-P4 בתצוגה, בצריכה, או בתיעוד | D14 + נתיב API נבדל + `target_definition` |
| R10 | ה-Holdout אינו בלתי-נגוע (EDA קדם בפאזה 5) | D11 — מתועד במפורש, ⛔ לא נטען כטענה אחרת |
| R11 | `cat_features` בבנאי ⇒ `RuntimeError` באמצע ה-search | D7 + קריטריון 16 |
| R12 | העתקת `max_iter=5000` מ-P3 במקום `50000` מ-P4 | D7 — נוקב במפורש בשורה 982 |
| R13 | `NaN` עתידי בנתוני מקור שהופך לשלילי בשקט דרך `NaN >= 34` | D16 + קריטריון 18 |
| R14 | ניסיון עתידי לאחד את שני טיפוסי ה-OOD ⇒ `TypeError` בזמן ריצה | D19 + קריטריון 22 |
| R15 | נתיב שביעי בלי 500/503 ⇒ סתירה מול שלושת ה-POST הקיימים ומול תכנון D7 בפאזה 9 | D20 + קריטריון 23 |

---

## ט. השפעה על פאזות אחרות

| פאזה | השפעה |
|---|---|
| **9** | שבעה נתיבים במקום שישה; `app/api_contract.py` משרת גם את `super-customer`; loader ל-P4S באותו מנגנון single-flight נעול. ⚠ **תכנון פאזה 9 הקיים נבחן מחדש** בעקבות ההרחבה — ר' `docs/planning/codex-review.md` חלק ג |
| **11** | תצוגת `Math.round(p*100)` (D15ב); ההסתייגות הקבועה (§א) מוצגת לצד הציון; הבחנה ויזואלית ברורה מפאנל `referral` |
| **12** | B41 (ר' `docs/planning/REQUIREMENTS.md`, `verifier=12`) נבדק **במסע באפליקציה החיה**, ⛔ לא רק ב-`metrics.json` |
| **13** | B43 ("How could Northbound spot them earlier?") נענה מ-P4S; B63 (הצדקת דליפה, `owner=8A`) נסגר רק אחרי שהמניעה מתועדת כאן במפורש (§ד); ⛔ שאר חובות הכתיבה (B29b/c, B32, B37a–d, B53a/b) **נשארות בפאזה 13** ואינן נדחות לכאן |

**חמש שאלות המייסדת (§02 בבריף):** התוכנית מאפשרת לענות על כולן באופן
אחראי בגבולות הנתונים. שאלות 1–3 מקבלות חיזוי הסתברותי/כמותי המבוסס
על הקשר קמפיין, ולכן רמת הפרסונליזציה מוגבלת ומוצהרת; שאלה 3
("Who will become a super customer") מקבלת כאן, לראשונה, מודל ייעודי
במקום הסתמכות על `P4` בלבד; שאלה 4 נענית רק בין ארבע האסטרטגיות
שנבדקו; שאלה 5 מספקת ראיה תיאורית והמלצה לניסוי, לא הוכחה סיבתית.

---

## י. סבבי האפיון ומעמד המסמך

### סבבי אפיון D1–D21

האפיון עבר **שישה סבבים** מול Codex (08–09.09.2026), כל אחד עם ממצא
שנבדק בהרצה ולא הונח:

**סבב 1** קבע את הגבולות הראשוניים (אוכלוסייה, תווית, ארבעת הפיצ'רים,
שלוש הטענות האסורות). **סבב 2** תיקן שגיאה מהותית: הדרישה "לא לחפוף
Holdouts אחרים" הוחלפה בדרישת "זרות פנימית" (D4) אחרי שהתברר
שהאוכלוסיות זהות מבנית; `seed=46` הוחלף ב-`48` אחרי שהתגלה
ש-`BOOTSTRAP_SEED=47` תפוס גם הוא; טענת "רק CatBoost מקבל `budget_tier`"
תוקנה לשני המועמדים. **סבב 3** נעל את `LogisticRegression(max_iter=50000)`
במפורש (לא `5000` של P3), ואת `ad_budget` כגבול קבוע מ-SPEC ולא נגזר
מ-train (D13) — לאחר אימות שהערכים מתלכדים בפועל אך הכלל שונה.
**סבב 4** הוסיף את D19–D21 (טיפוס האזהרה הייעודי, קודי 500/503 בחוזה
הנתיב, ומסלול `--run-p4s` המבודד) — שלושתם ממצאים שלא הועלו בסבבים
הקודמים. **סבב 5** אימת שני ממצאים חדשים אמפירית: `isinstance(w, OODWarning)`
מחזיר `True` דרך הירושה, ואיסור נעול על איחוד discriminated union.
**סבב 6** היה סנכרון תיעודי סופי — הרחבת התקציר לאפיון עצמאי ומלא,
תיקון מניינים (24 קריטריונים, 15 סיכונים), והחלפת הכותרת "טרם נכתב"
בהפניה לגוף המסמך שכבר קיים.

### מעמד
✅ **הכרעות D1–D21 אושרו בשישה סבבי אפיון, 09.09.2026.**
✅ **Codex ביצע ביקורת עצמאית ואישר את התכנון ללא ממצאים נוספים** בתום
הסבב השישי.
✅ **המשתמש אישר במפורש את התכנון** (09.09.2026): `planning_status`
עודכן ל-`approved_for_execution`. ✅ **המשתמש נתן הוראת ביצוע נפרדת ומפורשת**
באותה הודעה: לבצע את הפאזה במלואה על הענף `feat/super-customer`.
⚠ **ההוראה כללה איסור מפורש על commit/push/PR/merge** עד הוראה נוספת נפרדת —
כל הביצוע נשאר כשינויים לא-מקומיטים בעץ העבודה, לביקורת Codex לפני
כל פעולת git בלתי-הפיכה.

### ביקורת ביצוע — סבב 2 (Codex, 09.09.2026)

Codex בדק את הביצוע בפועל (447/447, אוכלוסייה/פיצולים, תתי-עצים ישנים
ב-`metrics.json`, טעינת `P4S.joblib` וחיזוי) ומצא ארבעה ממצאים, כולם
תוקנו באותו יום, **ללא commit**:

1. **חוסם provenance** — `P4S.meta.json` הצביע ל-`09aa052`, commit שאינו
   מכיל את קוד P4S (אותה מלכודת, `PHASE6.md:814–818`). **תוקן**: checkpoint 8
   סומן במפורש כארטיפקט זמני שאינו לפריסה, ממתין לבנייה מחדש **אחרי** commit
   נפרד לקוד+בדיקות בלבד, worktree נקי, ואז `--run-p4s` מחדש מ-HEAD החדש.
   לא זויף SHA, לא הורץ שוב כעת.
2. **כיסוי בדיקות חלקי לקריטריונים 10/24** — `test_write_p4s_artifact_never_
   calls_a_holdout_function` בדק רק checkpoint 8, לא את `_run_p4s()` עצמו.
   **תוקן**: נוספה `test_run_p4s_calls_holdout_evaluate_p4s_exactly_once_and_
   never_touches_the_other_tasks` שמריצה את `_run_p4s()` האמיתי עם mocks
   לכבדים/לכתיבה, ומוכיחה קריאה יחידה ל-`holdout_evaluate_p4s` ואפס קריאות
   לפונקציות אימון/Holdout של P2/P3/P4/P6 — אומת גם ב-negative control
   (הזרקת קריאה כפולה והזרקת קריאת `train_p2` תועה, שתיהן מפילות את הבדיקה).
   ניסוח הבדיקה הקודמת תוקן כדי לא לטעון כיסוי "by extension".
3. **B63 בסטטוס `planned`** — הפאזה עצמה קובעת שהוא נסגר אחרי תיעוד מניעת
   הדליפה (קיים בסעיף ד למעלה). **תוקן**: `docs/planning/REQUIREMENTS.md`
   עודכן ל-`done` עם ראיה מפורשת ל-§ד של מסמך זה; `tests/test_requirements_
   traceability.py`'s `_EXPECTED_STATUS_COUNTS` ו-ROADMAP.html's summary card
   עודכנו יחד (`done=44`, `planned=17`).
4. **דיווח מצב לא מדויק** — נטען שכל 11 ה-checkpoints הושלמו, בעוד checkpoint 8
   ממתין לבנייה מחדש ו-checkpoint 11 ממתין לביקורת ולפעולות Git. כרטיס פאזה 9
   ב-ROADMAP.html עדיין תיאר שישה נתיבים. **תוקן**: מעמד המסמך (למעלה) והכרטיס
   ב-ROADMAP.html עודכנו; פאזה 9 מתארת כעת שבעה נתיבים כולל
   `/api/predict/super-customer`, `planning_status` נשאר `planning_in_progress`
   בלי תכנון מחדש מלא.

### ביקורת ביצוע — סבב 3 (Codex, 09.09.2026)

Codex עדכן ישירות את `ROADMAP.html` (ארבעת סעיפי התקציר של 8A הוחלפו ב-11
ה-checkpoints האמיתיים: 9 `done`, checkpoint 8 ו-11 כ-`awaiting_approval`).
אימת `448/448`, תיקוני provenance/B63/פאזה 9, syntax JS ו-`git diff --check`.
נותרו שני ממצאים, שני התוקנו **ללא commit**:

1. **רשימת ה-boom-trap בבדיקת `_run_p4s()` כיסתה רק את המסלול הראשי** —
   ארבעת פונקציות האימון + חמש פונקציות ה-Holdout, אך לא את פונקציות
   הצינור הישן המשניות/מחקריות/הארטיפקט. **תוקן**: נוספו לרשימה
   `train_p3_weighted_comparison`, `train_p3_brief_rule`,
   `train_p3_operational_rule`, `train_p6_guardrail`, `train_p2_conformal`,
   `p6_bootstrap_simulation`, `train_p6_log1p_smearing`,
   `train_p4_early_funnel`, `train_p4_population_sensitivity`,
   `p6_duplicate_sensitivity`, `build_all_artifacts`, `_run_checkpoint_15`
   — 21 שמות חסומים בסך הכול. `tr._run_p4s()` עדיין מסתיים בהצלחה, מוכיח
   שאף אחת מהן לא נקראת בפועל.
2. **התיעוד עדיין הציג `447/447`/"17 בדיקות חדשות"** — לאחר הוספת בדיקת
   ה-orchestration בסבב 2 המספר האמיתי כבר היה `448/448` (18 חדשות: 8+5+5).
   **תוקן**: כל המופעים העדכניים (checkpoint 11, כרטיס 8A ב-ROADMAP.html)
   עודכנו ל-`448/448`/18/5; המופע ב"ביקורת ביצוע — סבב 2" למעלה נשאר
   `447/447` במכוון — זהו תיאור היסטורי מדויק של מה שסבב 2 בדק בפועל
   באותו רגע, לא טענת מצב נוכחי.
