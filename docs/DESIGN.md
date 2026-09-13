# FunnelIQ — מפרט מערכת עיצוב

> **תוצר פאזה 10** (`docs/planning/PHASE10.md` D6). מקור האמת ל**כללים** —
> רכיבים, מצבים, כללי שימוש ומיפוי מסכים. ערכי ה-tokens בפועל נמצאים
> ב-`app/static/tokens.css` (checkpoint 3); הקובץ הזה מגדיר *אילו* טוקנים
> קיימים ו*מתי* משתמשים בהם, ⛔ לא את ערכיהם המספריים.
>
> ⛔ **אין כאן קוד, HTML/CSS/JS בפועל, וחיווט לנתונים** — אלה פאזה 11.
> `docs/IA.md` נשאר מקור האמת ל**תוכן ולהתנהגות**; מסמך זה מוסיף מפרט
> **חזותי** בלבד ואינו משכפל לוגיקה עסקית.
>
> **נכתב ב-checkpoint 1:** מלאי הרכיבים, מלאי המצבים ומיפוי המסכים.
> **נכתב ב-checkpoint 2:** מטריצת שדה חוזה → רכיב, מול `app/schemas.py`.
> **נכתב ב-checkpoint 5:** פריסות Desktop ומפרט Dataviz (§3.4, §4.1).
> **נכתב ב-checkpoint 6:** מטריצת D9 בת שש העמודות, מפת שדות קלט (D11)
> ומסע המשתמש (§6–§8). **נכתב ב-checkpoint 9:** צילומי ששת המסכים
> (`docs/design/`) ומטריצת הכיסוי (§9), אחרי reference חזותי מ-Stitch
> ותיקון checkpoint 8. **checkpoints 8–9: `done`.**
> **עודכן בפאזה 10A, CP5:** שפה מוצרית גנרית, זרימת דוגמה/סיכום/עריכה,
> `not_closed` מחושב, אישורי הקשר וקיפול תוצאות הוגדרו לפני תיקון המימוש.

---

## 0. ששת המסכים — מפה

| # | מסך | תוכן עיקרי | מקור מפרט |
|---|---|---|---|
| 1 | Login | קיים מפאזה 4 — מבנה/תוכן ללא שינוי; המראה מיושם בפאזה 11 | `IA.md` §1, `PHASE10.md` D4 |
| 2 | Overview | אינדקס חמש יכולות עסקיות + טבלת רמות הוצאה + גרף המרה | `IA.md` §2, `PHASE10.md` D8, מסך 2 |
| 3 | טופס חיזוי משותף (P2·P3·P4) | 12 שדות להזנה + ערך מחושב, דוגמה אופציונלית, שלושה פאנלי תוצאה | `IA.md` §3, `PHASE10.md` מסך 3 |
| 4 | ציון לקוח-על מוקדם (P4S) | 4 שדות, הזנה ידנית כמסלול ראשי, פאנל תוצאה עצמאי | `IA.md` §3א, `PHASE10.md` D7ב/ד7ג/מסך 4 |
| 5 | Budget Simulator | הודעת חפיפה + 4 אסטרטגיות + גרף דירוג | `IA.md` §6, `PHASE10.md` מסך 5 |
| 6 | Follow-up | גרף נשירה + גרף `calls_to_closed` + המלצת מדיניות | `IA.md` §7, `PHASE10.md` מסך 6 |

---

## 1. מלאי רכיבים

כל רכיב מזוהה בשם קבוע (kebab-case, לשימוש עתידי כ-CSS class/component name
בפאזה 11) ומצהיר אילו טוקנים סמנטיים הוא צורך (§3). ⛔ אין ערכים כאן — רק
שמות טוקנים.

### 1.1 — רכיבי תוצאת חיזוי

| רכיב | שימוש | טוקנים נצרכים |
|---|---|---|
| `prediction-primary` | התוצאה הראשית של פאנל חיזוי — מספר/אחוז חי בולט (`{X} חודשים`, `{Y}%`, `{Z} מתוך 100`) | טיפוגרפיה ראשית; ⛔ **אינו** `--color-positive`/`--color-negative` בשום פאנל תחזית (D10) |
| `prediction-range` | טווח משני גלוי ל-P2 (`{Y}–{Z} חודשים`, בלי אחוז; שני הגבולות מאותה תגובה) | `--color-uncertain`, whisker |
| `propensity-band-badge` | תווית קטגוריה `below_base`/`near_base`/`above_base` (מקור: `IA.md` §4) — P3, P4, P4S | טקסט + אייקון (⛔ לא צבע בלבד), `--color-uncertain` נייטרלי |
| `base-rate-line` | ⚠ **נוסף ב-checkpoint 2**, כתוצר ישיר של מיפוי `base_rate` מול `app/schemas.py` — לא היה לו רכיב בכלל בגרסת checkpoint 1. שורת השוואה משנית: `event_probability` מול `base_rate` + הפרש בנקודות. P3/P4/P4S | — |
| `evidence-badge` | תג רמת ראיות — שתי רמות (P2/P3/P4/P4S: `low`/ריק) או שלוש (P6: `high`/`medium`/`low`). ⚠ **כשהרמה `low`, הרכיב נושא גם את הודעת `UnobservedBudgetWarning`** (הערך שלא נצפה) — לא רק תג ריק (§5.1–§5.3) | `evidence-high` · `evidence-medium` · `evidence-low` |
| `calibration-badge` | תג `calibrated`/`uncalibrated` — **גם ב-P4S**, אך שם **נעול ל-`calibrated` בלבד**; `uncalibrated` אפשרי רק ב-P3/P4 (ר' §2.4) | `calibrated` · `uncalibrated` |
| `model-disclaimer` | הסתייגות גלויה בשפה פשוטה (P2 מנוף, P4 הבהרת proxy, P4S אומדן-לא-הבטחה) | `model-disclaimer`, טיפוגרפיה משנית שאינה מוסתרת |
| `model-details` | `<details>` סגור כברירת מחדל — גרסה, אלגוריתם, מדדים ושיטת אינטרוול/כיול בלבד; ⛔ אין בו תנאי שימוש או מגבלה שמשנה החלטה | — |
| `prediction-panel` | מיכל פאנל חיזוי. **משותף לכל משימה:** `prediction-primary`+`evidence-badge`+`model-disclaimer`+`model-details` (מקור: `IA.md` §8, "שדות משותפים לכל תשובות החיזוי"). **לכל משימה ילדים נוספים משלה, ⛔ לא אחידים בין המשימות** (מקור: `IA.md` §3.4/§3א.4; פירוט הכיול הספציפי — §2.4): **P2** מוסיף `prediction-range` בלבד (⛔ אין לו `propensity-band-badge`, `base-rate-line` או `calibration-badge` — רגרסיה, אין מכייל ואין שיעור בסיס) · **P3/P4** מוסיפים `propensity-band-badge`+`base-rate-line`+`calibration-badge` (⛔ אין להם `prediction-range` — מסווגים, אין טווח חיזוי) · **P4S** מוסיף `propensity-band-badge`+`base-rate-line`+`calibration-badge` (נעול `calibrated`)+`business-context-card` (⛔ אין `prediction-range`). שלושת הווריאנטים נושאים בעצמם את `panel-loading`/`panel-error` ברמת הפאנל (§2.1) | — |
| `business-context-card` | כרטיס הקשר עסקי במסך P4S בלבד — פרופיל לקוחות-העל (מקור: `IA.md` §3א.6) | `model-disclaimer` (מבנה דומה), טקסט קבוע |
| `panel-error` | שגיאה בשלושה סוגי היקף: **ברמת מסך שלם** — ארבעה מסכים (Login, Overview, Follow-up, Budget Simulator) · **ברמת פאנל בודד** בתוך `prediction-panel` וריאנט הטופס המשותף (הפאנלים האחרים ממשיכים) · **ברמת הפאנל היחיד** של `prediction-panel` וריאנט P4S. כל ההיקפים משתמשים באותו רכיב, ר' מטריצת §2.1 | `role="alert"`, `--error-fg`, `--error-bg` |

### 1.2 — רכיבי מצב-מערכת (חוצי-מסכים)

| רכיב | שימוש | טוקנים נצרכים |
|---|---|---|
| `panel-loading` | טעינה — `role="status"` | — |
| `panel-empty` | הסבר "מה חסר ומה לעשות"; ⛔ לעולם לא מסך ריק ללא טקסט | — |
| `ood-banner` | פאנל/מסך מחוץ לתחום — הודעה + סיבה קונקרטית, **בלי מספר** | `out-of-distribution` |
| `auth-redirect` | 401 — הפניה למסך Login + הודעה; תוכן טופס לא נשמר | `role="alert"`, `--error-fg`, `--error-bg` |
| `forbidden-notice` | 403 — הודעת חוסר הרשאה; ⛔ בלי נתונים, בלי ניסיון חוזר, בלי חזרה ל-Login; sign-out זמין | `role="alert"`, `--error-fg`, `--error-bg` |

### 1.3 — רכיבי טופס קלט

| רכיב | שימוש | טוקנים נצרכים |
|---|---|---|
| `field-input` | רכיב בסיס בשני וריאנטים: **וריאנט חיזוי** — `<input type="number" step="1" min="0" required>`, שדה מספר שלם/סופי/אי-שלילי (12 שדות נערכים בטופס המשותף, 4 שדות P4S). בפוקוס: כל התוכן נבחר אוטומטית (`onfocus="this.select()"`) — משותף לשני הטפסים, מקל על דריסת ערך דוגמה בהקלדה אחת · **וריאנט Login** — `<input type="email" required>`/`<input type="password" required>`, ⛔ בלי הגבלות המספר השלם של וריאנט החיזוי ו⛔ בלי בחירה אוטומטית בפוקוס | — |
| `field-label` | רכיב בסיס בשני וריאנטים: **וריאנט חיזוי** — תווית עסקית בעברית + שם טכני משני + יחידה (D11, §2.5) · **וריאנט Login** — תווית רגילה בעברית (`אימייל`, `סיסמה`) בלבד, ⛔ בלי שם טכני ובלי יחידה — D11 חל רק על שדות חיזוי | — |
| `prefill-picker` | בורר טעינת דוגמה היסטורית — **שני מופעים נפרדים**: אחד לטופס המשותף (§3.3), אחד ל-P4S (§3א.3) | — |
| `context-confirmation` | אישור קצר מחוץ לקלטי המודל: רכישה וסוף קמפיין בטופס המשותף; רכישה, השלמת מעקב 1 וסגירת חלון חודשי ב-P4S. נדרש לתרחיש עצמאי/נערך, ⛔ אינו נשלח או נשמר | — |
| `scenario-status` | תווית מקור: `תרחיש עצמאי` / `דוגמה היסטורית` / `תרחיש שנערך`; ללא שם לקוח או `source_row_id` גלוי | — |
| `input-summary` | דו-וריאנטי: **וריאנט טופס משותף** — מקור, `n/12` והערך המחושב · **וריאנט P4S** — מקור, `n/4`, ובמצב `תרחיש שנערך` גם מונה שדות ששונו; ⛔ בלי ערך מחושב. שניהם נשארים גלויים גם כשאזור העריכה מקופל (`IA.md` §3.3/§3א.3.1) | — |
| `revert-field-action` | `החזר לערך הדוגמה` פר-שדה, P4S בלבד — מוצג **רק** ליד שדה שנערך וכשקיימת דוגמה טעונה. מחזיר ערך יחיד; ⛔ אינו קורא ל-Supabase, ⛔ אינו מוצג כמושבת בתרחיש עצמאי (`IA.md` §3א.3.1) | — |
| `clear-form-action` | `נקה טופס` — **משותף לשני הטפסים** (⚠ מחליף את `איפוס שדות` שהופיע במוקאפ הטופס המשותף ללא מקור קנוני, באותו אופן שהחליף `Reset Fields` ב-P4S). **טופס משותף:** מאפס 12 השדות הנערכים ומאפס `input-summary` ל-`תרחיש עצמאי · 0/12 · לא הומרו: —`; `not_closed` אינו נכתב ישירות — מתרוקן נגזרתית מהיעדר מקורותיו; מונה הדור המשותף עולה ופוסל את שלוש הבקשות; `input-details` נפתח מחדש. **P4S:** מאפס ארבעה שדות, דוגמה, אישור הקשר ותוצאה, ומאפס את `input-summary` ל-`תרחיש עצמאי · 0/4`. **בשני הטפסים: דורש אישור כשקיים ערך, דוגמה, עריכה, תוצאה או בקשה בתהליך**; ישיר רק בטופס ריק לחלוטין. ביטול האישור ⛔ אינו משנה מצב (`IA.md` §3.3.1/§3א.3.1) | — |
| `input-details` | `<details>` בשם `בדיקה ועריכת נתונים`; פתוח כברירת מחדל בתרחיש ריק וסגור אחרי טעינת דוגמה תקינה | — |
| `derived-field` | `not_closed` לקריאה בלבד: מציג `followup_5 - closed`, שני מקורות והערך; מצב שלילי מוצג כשגיאה וחוסם שליחה | — |
| `submit-blocked-message` | הודעת כלל ולידציה חוסם (חמישה כללים לטופס המשותף; ארבעה ל-P4S — §2.5) | — |

### 1.4 — רכיבי ניווט, מעטפת משתמש ותוכן-עמוד

⚠ **קבוצה נוספה** — מכסה את Login, המעטפת המחוברת, ניווט ו-sign-out
(`PHASE10.md` D4, `contributor=10` על `B10`/`B56`), שהיו חסרים ממלאי
הרכיבים המקורי. ⛔ אין כאן התנהגות חדשה — רק מיפוי חזותי למה שכבר קיים
ומאושר (Login קיים מפאזה 4; session/nav/sign-out נדרשים ב-B10/B56).

| רכיב | שימוש | טוקנים נצרכים |
|---|---|---|
| `login-form` | מסך 1 — שני `field-input`/`field-label` בווריאנט Login (email, password) + כפתור שליחה; מבנה, תוכן ולוגיקה **ללא שינוי** (D4). ⛔ **מחוץ ל-`authenticated-shell`** — לפני התחברות אין session | — |
| `authenticated-shell` | המעטפת סביב **מסכים 2–6 בלבד** (Overview · טופס משותף · P4S · Simulator · Follow-up) לאחר התחברות מוצלחת — עוטפת `app-nav` ו-`sign-out-control`; קיומה הוא התשובה החזותית ל-B10 ("signed-in user reaches the dashboard") | — |
| `app-nav` | ניווט בין **חמשת המסכים המחוברים — מסכים 2–6**, בתוך `authenticated-shell` (B56 — "login-gated dashboard"). ⛔ **אינו כולל את Login** (מסך 1) — הוא מחוץ למעטפת ואין אליו ניווט-חזרה מתוכה | — |
| `sign-out-control` | פקד יציאה — **זמין תמיד** במעטפת המחוברת, **כולל** במצב `forbidden-notice` (403, §2.6) | — |
| `capability-index` | אינדקס חמש יכולות עסקיות ב-Overview — חמישה כרטיסים גנריים לארבעה יעדים (D8); ⛔ ללא “שאלות המייסדת” או קודי משימה בטקסט המוצר | — |
| `tier-table` | טבלת רמות הוצאת פרסום חודשית ב-Overview; שורת `gap` מסומנת בנפרד | `color-tier-1` · `color-tier-2` · `color-tier-3` |
| `overlap-alert` | הודעת חפיפת שתי האסטרטגיות המובילות ב-Simulator — **הרכיב הבולט ביותר במסך** | `--color-uncertain` |
| `strategy-row` | שורת אסטרטגיה בסימולטור — רווח + טווח + `n` + רמת ראיות | `evidence-high` · `evidence-medium` · `evidence-low` |
| `summary-recommendation` | רכיב D9 בן ארבע שכבות — תשובה / מה זה אומר / מה כדאי לעשות / חשוב לדעת. התשובה, המשמעות העסקית, הפעולה והמגבלה המהותית גלויות; פירוט מתודולוגי משני עובר ל־`model-details` | `model-disclaimer` לשכבת "חשוב לדעת" |
| `chart-live` | גרף SVG חי — ארבע מופעים (§4). **ה-fallback הטבלאי הנגיש הוא חלק מהרכיב עצמו, ⛔ לא רכיב נפרד** — `chart-live` תמיד מרנדר את שניהם יחד | ≤5 צבעים סמנטיים |

---

## 2. מלאי מצבים

⚠ **כל מצב ב-`IA.md` §9 מופיע כאן** (דרישת קבלה של checkpoint 1).

### 2.1 — מצבים לכל מסך (מקור: `IA.md` §9.1)

| מסך | `loading` | `empty` | `error` | `OOD` |
|---|---|---|---|---|
| **Login** (`login-form`) | בדיקת session + טעינת `/api/config` — `panel-loading` | ⛔ לא רלוונטי | כשל `/api/config` → `panel-error` ברמת מסך; כשל התחברות → הודעה בטופס | ⛔ לא רלוונטי |
| **Overview** | טעינת `budget-tiers` — `panel-loading` | ⛔ **אין `empty` לגיטימי** — `200` עם אפס שורות הוא שגיאת זמינות, מוצג כ-`panel-error` | `panel-error` + ניסיון חוזר; ⛔ אין הצגת נתונים חלקיים | ⛔ לא רלוונטי |
| **טופס חיזוי משותף** (שלושה `prediction-panel`) | טעינת דוגמה מציגה `panel-loading` בעזר בלבד, בלי לנעול קלט ידני; שלוש בקשות החיזוי חולקות דור אחד | ללא דוגמה: `input-details` פתוח ו־`input-summary` מציג התקדמות; דוגמה טעונה: פרטים סגורים; אפס דוגמאות אינו חוסם מילוי; `נקה טופס` מחזיר למצב הזה | כשל דוגמה מקומי שומר קלט; כשל חיזוי **פר-פאנל** — `panel-error` בפאנל שנפל ושני האחרים ממשיכים | ✅ **פר-פאנל** — `ood-banner`; תשובה/פעולה/מגבלה נשארות גלויות |
| **ציון לקוח-על (P4S)** (`prediction-panel` וריאנט P4S) | טעינת דוגמה נפרדת אינה נועלת ארבעה שדות; בקשה אחת בדור עצמאי | ארבעת השדות וה־`context-confirmation` זמינים ללא דוגמה; אפס דוגמאות אינו חוסם; `input-summary` וריאנט P4S מציג `תרחיש עצמאי · 0/4`; `נקה טופס` מחזיר למצב הזה | כשל דוגמה מקומי; כשל חיזוי בפאנל היחיד — `panel-error` + ניסיון חוזר | ✅ **על ארבעת שדותיו בלבד** — `ood-banner`; תנאי הרוכש והזמן גלויים גם בלי ציון |
| **Follow-up** | טעינת שני חלקי ה-endpoint — `panel-loading` | ⛔ אפס שורות אינו `empty` — שגיאת זמינות; גם אי-סגירות בסכום התדירויות | `panel-error` + ניסיון חוזר; חלק אחד נפל → השני ממשיך עם ציון מה חסר | ⛔ לא רלוונטי |
| **Budget Simulator** | טעינת ארבע האסטרטגיות — `panel-loading` | ⛔ תשובה ריקה = כשל, לא "אין אסטרטגיות" | `panel-error` + ניסיון חוזר | ⚠ **בלתי אפשרי מבנית** (§2.2) |

כלל רוחבי: `panel-loading` תמיד `role="status"`, `panel-error`/`forbidden-notice`
תמיד `role="alert"`, שניהם בעברית. `panel-empty` תמיד מסביר מה חסר ומה
לעשות.

### 2.2 — OOD ברמת הפאנל (טופס משותף — מקור: `IA.md` §9.2)

`ood_bounds` שונים בין P2/P3/P4 (שבעה מ-13 הפיצ'רים נבדלים) — אותה רשומה
יכולה להיות בתחום לפאנל אחד ומחוצה לו לאחר. `ood-banner` יושב **על כל
פאנל בנפרד**; באנר משותף רק כששלושת הפאנלים מסכימים.

בפאנל OOD: `אין מספיק נתונים לחיזוי אמין` + הסיבה הקונקרטית (איזה שדה,
מחוץ לאיזה גבול) + ⛔ **בלי מספר**. שני הפאנלים האחרים ממשיכים לפעול.

⚠ ערך פנימי שלא נצפה **אינו** OOD — מקבל חיזוי מלא + `evidence-badge`
ברמת `low` + `warnings`.

⚠ Budget Simulator: `in_training_domain` קבוע `true` לסט האסטרטגיות
הקבוע — `ood-banner` **אינו נגיש** במסך הזה מבנית (`IA.md` §6.1).

### 2.3 — OOD של P4S (מקור: `IA.md` §9.2א)

⛔ **אין להשתמש בגבולות 13 השדות של הטופס המשותף.** `ood-banner` במסך
P4S בודק **ארבעה** פיצ'רים בלבד (`ad_budget`, `num_leads`,
`leads_answered`, `followup_1`), גבולות נפרדים מ-`models/P4S.meta.json`.

⚠ רשומה יכולה להיות בתחום ל-P4S ומחוצה לו לטופס המשותף, ולהפך — הם
בודקים סטים שונים של פיצ'רים. ⛔ אין `ood-banner` משותף בין שני המסכים.

### 2.4 — כיול והבחנה P4/P4S (מקור: `IA.md` §3.4/§3א.4/§3א.5)

`calibration-badge` מציג `calibrated`/`uncalibrated` ב-P3/P4. ⛔ **במסך
P4S `calibration-badge` נעול ל-`calibrated` בלבד** — `uncalibrated`
לעולם אינו מופיע שם.

הבחנה P4↔P4S היא **מבנית וטקסטואלית**, ⛔ לא צבעונית: כותרת שונה
("נטייה להפניה" מול "ציון לקוח-על מוקדם"), יחידה שונה (`{X}%` מול `{Y}`),
מסך נפרד. ⛔ ל-P4S אין `prediction-range` — אין `lower_bound`/`upper_bound`
בסכמה שלו.

### 2.5 — ולידציה חוסמת (מקור: `IA.md` §3.2/§3א.2)

| מסך | כללים | תגובה |
|---|---|---|
| טופס משותף (13 ערכי payload, ‏12 נערכים) | 5 כללים: `num_leads>0` · `leads_answered≤num_leads` · שרשרת יורדת `leads_answered≥followup_1≥…≥followup_5` · `derived-field = followup_5-closed≥0` ושומר את זהות החוזה · אי-שליליות/שלמות. תרחיש עצמאי או נערך דורש גם `context-confirmation` | `submit-blocked-message`, חוסם שליחה — ⚠ **אינה** בדיקת OOD; ⛔ אין חיתוך לאפס או תיקון שקט |
| P4S (4 שדות) | 4 כללי מספר: `num_leads>0` · `leads_answered≤num_leads` · `followup_1≤leads_answered` · אי-שליליות; לפני תרחיש עצמאי/נערך נדרש גם `context-confirmation`, שאינו פיצ'ר חמישי | `submit-blocked-message`, חוסם שליחה |

### 2.6 — 401 מול 403 (מקור: `IA.md` §9.3)

| קוד | רכיב | תוכן |
|---|---|---|
| 401 | `auth-redirect` | אין session/פג תוקף → מסך Login + הודעה; תוכן הטופס **אינו** נשמר |
| 403 | `forbidden-notice` | מאומת בלי `organization=northbound` → הודעת חוסר הרשאה, ⛔ בלי נתונים, בלי ניסיון חוזר, בלי חזרה ל-Login; `sign-out-control` נשאר זמין בתוך `authenticated-shell` |

### 2.7 — תשובות מאוחרות ומוני דור (מקור: `IA.md` §9.4/§9.4א)

| מסך | מונה דור | עולה ב |
|---|---|---|
| טופס משותף (P2+P3+P4) | **אחד משותף** לשלוש הבקשות | שינוי אחד מ־12 השדות הנערכים/הערך המחושב · שינוי אישור ההקשר · בקשת דוגמה אחרת · אישור `נקה טופס` (⛔ לא הביטול) · יציאה מהחשבון |
| ציון לקוח-על (P4S) | **עצמאי, נפרד לחלוטין** | שינוי אחד מארבעת שדות P4S · שינוי אישור ההקשר · בקשת דוגמה אחרת בבורר הנפרד · `החזר לערך הדוגמה` · אישור `נקה טופס` (⛔ לא הביטול) · יציאה מהחשבון |

⛔ תגובה שהמונה שלה אינו הנוכחי נזרקת בשקט, לא מרונדרת. ⛔ מונה משותף בין
שני הטפסים אסור — הוא היה גורם לבקשת מסך אחד לפסול תשובה תקפה של השני.
יציאה מהחשבון זונחת את כל הבקשות שבאוויר בשני המסכים, ללא תלות במונים.

---

## 3. פלטה סמנטית וטוקני מצב — מלאי, ללא ערכים

⚠ ערכים מספריים (hex, px, rem) נכתבים ב-`app/static/tokens.css`
(checkpoint 3) ומאומתים בבדיקה האוטומטית (checkpoint 4). כאן — מלאי
השמות והכללים בלבד.

### 3.1 — פלטה סמנטית (מקור: `PHASE10.md` §ו, `SPEC.md` §Design tokens)

| טוקן | משמעות | D10 |
|---|---|---|
| `--color-primary` | מותג | — |
| `--color-positive` | **תוצאה שנצפתה בנתונים**: סגירה, אפסייל שקרה, הפניה שניתנה, לקוח-על בפרופיל היסטורי | ⛔ אסור על תחזית/הסתברות |
| `--color-negative` | תוצאה שלילית שנצפתה: נשירה, לא נסגר | ⛔ אסור על תחזית/הסתברות |
| `--color-uncertain` | **תחזית או הסתברות** — P2, P3, P4, P4S, רווח צפוי ב-P6. ⚠ ניטרלי/ענברי, ⛔ לא ירוק/אדום | חובה על כל תחזית, ⛔ ללא יוצא מן הכלל |
| `--color-muted` | טקסט משני/הסתייגות — הבסיס ל-`model-disclaimer` | — |
| `--color-text` | טקסט גוף רגיל | — |
| `--color-bg` | רקע העמוד — הרקע שמולו נבדקים כל מילויי הגרפיקה (בדיקות 2–3) | — |
| `color-tier-1` · `color-tier-2` · `color-tier-3` (כל אחד זוג `-fg`/`-bg`) | רמות הוצאה נמוכה/בינונית/גבוהה — **סדרה מסודרת** (רמפה עוקבת, לא שלושה גוונים בלתי-קשורים), כרקע `tier-table` בלבד | — |

⛔ **כלל D10, חוצה-מסכים:** `prediction-primary` בכל ארבע משימות החיזוי
(P2/P3/P4/P4S) צורך **תמיד** `--color-uncertain`, **לעולם לא**
`--color-positive`/`--color-negative` ו⛔ **גם לא ניטרלי** — גם כשהתחזית "טובה". `ציון לקוח-על:
`{X}` בירוק משדר "זה כבר קרה", וזו בדיוק ההטעיה שהכלל אוסר.

### 3.2 — טוקני מצב

`evidence-high` · `evidence-medium` · `evidence-low` · `prediction-range`
(`--prediction-range-color`) · `model-disclaimer` · `out-of-distribution` ·
`calibrated` · `uncalibrated`.

טיפוגרפיה משנית לראיות ולהסתייגות — קטנה יותר, ⛔ לא קטנה עד כדי הסתרה
(`--model-disclaimer-font-size`).

⛔ **אין הסתמכות על צבע בלבד בשום מצב** — `ood-banner`,
`evidence-badge`, `calibration-badge`, `propensity-band-badge` מקבלים
תמיד גם טקסט וגם אייקון (`IA.md` §10).

⚠ **`--focus-outline`** — לא רכיב סטטוס-נתונים כמו האחרים, אלא מענה
ישיר לדרישת `IA.md` §10 "מקלדת: `focus` נראה תמיד". מוחל על כל פקד בר-מיקוד
(`field-input`, `app-nav`, `sign-out-control`, `prefill-picker`).

### 3.3 — מערכת ויזואלית (מקור: `PHASE10.md` §ו)

כולן נכתבות מאפס ל-FunnelIQ (לא ירושה ממערכת אחרת):

| קבוצה | טוקנים |
|---|---|
| טיפוגרפיה | `--font-family` (Rubik) · `--font-size-xs` · `--font-size-sm` · `--font-size-base` · `--font-size-lg` · `--font-size-xl` · `--font-size-2xl` (שש דרגות) |
| Spacing | `--space-1` · `--space-2` · `--space-3` · `--space-4` · `--space-6` · `--space-8` (רשת 4px) |
| Radius | `--radius-sm` · `--radius-md` · `--radius-lg` |
| Elevation | `--shadow-card` · `--shadow-popover` |
| רשת | `--grid-columns-desktop` · `--grid-gap` |

כיוון: `dir="rtl"`. מטבע: `he-IL` עם מפרידי אלפים. מספרים, מטבעות,
צירים ושמות שדות באנגלית — **LTR בתוך container RTL**.

### 3.4 — פריסת Desktop לכל מסך (checkpoint 5, מקור: `PHASE10.md` §ו)

פאזה 10 מגדירה **תצוגת Desktop בלבד**; זהו היקף התצוגה היחיד בפאזה.
הרשת משתמשת ב-`--grid-columns-desktop`
וב-`--grid-gap`; לכל טבלה מיכל `overflow-x` עצמאי כדי שלא תגרום לגלילת
הגוף גם בחלון Desktop צר מן הרגיל.

**קבוצת פריסה (layout group) — לא רכיב חדש:** בכל מסך שנושא `chart-live`,
הגרף ו-`summary-recommendation` **שלו** (D9, §6)
נשארים צמודים כיחידה אחת — אך "צמודים" אינו בהכרח "זה-לצד-זה": **הסידור
הפנימי של הקבוצה (זה-לצד-זה, או הגרף למעלה וההסבר מיד מתחתיו) תלוי אם
הקבוצה עצמה יושבת גם היא זה-לצד-זה עם רכיב אחר** (טבלה, קבוצה נוספת) —
⚠ **תוקן אחרי ביקורת עצמאית:** "זה-לצד-זה בתוך הקבוצה" כחוק גורף, יחד עם
הקבוצות עצמן זה-לצד-זה עם רכיבים אחרים, יצר שלוש/ארבע עמודות אופקיות
במסכים שבהם הקבוצה אינה לבדה ברוחב מלא (§ו אינו מגדיר יותר משתי עמודות
בשום מסך). הכלל המדויק לפי מסך רשום בטבלה למטה. אותו עיקרון (הסבר צמוד,
לא בהכרח לצדו) חל גם במקום שבו
`prediction-panel` נושא `summary-recommendation` משלו — שם נשאר **ללא
שינוי**: ההסבר בתוך הפאנל עצמו.

| מסך | פריסת Desktop |
|---|---|
| **Login** | `login-form` — כרטיס ממורכז, `width: 100%` עד `max-width` קיים (360px ב-`style.css`, ⛔ **ללא שינוי כאן** — D4); אינו רוחב קשיח שגולש |
| **מעטפת מחוברת** (`authenticated-shell`/`app-nav`/`sign-out-control`, מסכים 2–6) | `app-nav` אופקי בראש המעטפת, חמשת המסכים המחוברים זה-לצד-זה · `sign-out-control` גלוי תמיד בקצה הניווט |
| **Overview** | `capability-index` — רשת גמישה של 2–3 טורים לפי הרוחב הפנוי (למשל 3+2), ⛔ **לא** שורה קשיחה אחת של חמישה כרטיסים · מתחתיה `tier-table` · מתחתיו **קבוצת הפריסה**, ברוחב מלא; הגרף וההסבר שלו רשאים להיות זה-לצד-זה בתוכה |
| **טופס חיזוי משותף** | `context-confirmation` ו־`prefill-picker` בראש · אחריהם `input-summary` גלוי ו־`input-details` מתקפל שבתוכו 12 `field-input` ברשת ו־`derived-field` לקריאה בלבד · כפתור שליחה אחד · מתחתיו שלוש קבוצות פריסה זה-לצד-זה, כל `prediction-panel` עם `summary-recommendation` שלו |
| **ציון לקוח-על (P4S)** | `prefill-picker` נפרד בראש, ואחריו `input-summary` וריאנט P4S גלוי · ארבעת השדות בשורה אחת, בלי קיפול שנחוץ לטופס הגדול; `revert-field-action` צמוד לכל שדה שנערך · `context-confirmation` **בתחתית, ממש לפני כפתור השליחה** — ⚠ **שונה מהטופס המשותף** (שם הוא בראש עם `prefill-picker`), כי אישור P4S הוא רגע-לפני-שליחה ולא תנאי פתיחה · שני כפתורים זה-לצד-זה: שליחה ו־`clear-form-action` ("נקה טופס") · קבוצת הפריסה: `prediction-panel` וריאנט P4S + `summary-recommendation` שלו |
| **Budget Simulator** | `overlap-alert` ברוחב מלא למעלה · מתחת לו **שתי עמודות בלבד**: ארבעת `strategy-row` בטבלה בעמודה 1; Dataviz #2 למעלה וההסבר שלו מיד מתחתיו בעמודה 2 |
| **Follow-up** | **שתי קבוצות פריסה זו-לצד-זו**; בכל קבוצה הגרף (#3 או #4) למעלה ו-`summary-recommendation` שלו מיד מתחתיו |

⛔ **אין רכיבים חדשים בסעיף הזה** — רק סידור מרחבי (כולל "קבוצת פריסה", שאינה
רכיב אלא כלל סידור) של הרכיבים שכבר מוגדרים ב-§1/§4; שם רכיב שלא מופיע
ב-§1 או ב-§4 הוא טעות תיעוד.

---

## 4. Dataviz — מלאי תצוגות

מלאי התצוגות וכלליהן המחייבים (מקור: `PHASE10.md` §ו, `IA.md` §7); מפרט
הפריסה השולחנית — §4.1.

**ארבע תצוגות חיות**, כולן `chart-live` — SVG ידני ונגיש, ⛔ בלי ספריית
תרשימים:

| # | תצוגה | מסך |
|---|---|---|
| 1 | שיעור המרה לפי רמת הוצאת פרסום חודשית | Overview |
| 2 | דירוג ארבע אסטרטגיות התקציב | Budget Simulator |
| 3 | נשירה `followup_1`→`followup_5` | Follow-up |
| 4 | התפלגות `calls_to_closed` (גרף עמודות) | Follow-up |

**שתי משפחות offline** — ⛔ אינן בממשק, `REPORT.md` בלבד: עקומות כיול
(P3/P4/P4S) · SHAP summary ו-local.

**כללים משותפים לארבע החיות:** עד חמישה צבעים סמנטיים · עמודות מתחילות
באפס · grid עדין · אותה משפחת גופן/עובי קו/radius/פורמט מספרים · טווחי
אי-ודאות ב-whisker עם מקרא טקסטואלי · **fallback טבלאי נגיש לכל גרף חי**
(חובה, לא אופציונלי) · כותרות/צירים/מקרא/שמות feature **באנגלית**; הסבר/
caption/מסקנות/הסתייגויות סביב הגרף **בעברית**.

⛔ **לא לצייר:** 3D · עוגה · ציר כפול · גרדיאנטים דקורטיביים · אנימציות
מיותרות · צבע שונה לכל נקודה בלי משמעות סמנטית.

### 4.1 — פריסת Dataviz ב-Desktop (checkpoint 5, מקור: §3.4)

כל ארבע התצוגות החיות הן SVG עם `viewBox` (קנה-מידה יחסי) ו-`width: 100%`
של המיכל שלהן — **אין רוחב/גובה קשיחים בפיקסלים בקוד**; הגובה נגזר
מהרוחב לפי יחס-גובה-רוחב קבוע (`aspect-ratio`), לא ממידה מוחלטת, כדי
שהגרף יתאים לרוחב אזור התוכן השולחני שבו הוא יושב (§3.4).

| כלל | Desktop |
|---|---|
| יחס גובה-רוחב | **16:9** — רחב, מתאים לגרף שיושב לצד רכיב נוסף |
| Fallback טבלאי | מיכל `overflow-x` עצמאי כמו `tier-table`/`strategy-row`; לעולם לא גלילת גוף העמוד |
| גובה מזערי | ⚠ אין ערך פיקסלים כאן; תוויות ציר ומקרא לעולם אינן חופפות זו את זו |

---

## 5. מטריצת שדה חוזה → רכיב (F2, checkpoint 2)

⚠ **נבנתה מחדש מול `app/schemas.py` בפועל**, לא הועתקה מ-`IA.md` §8 —
אימות עצמאי, בהתאם לדרישת F2 המקורית שגילתה שהמטריצה בפאזה 7 נכתבה מול
חוזה שטרם ננעל. **הכלל (F2): לכל שדה שהדפדפן צורך יש רכיב מוצג או נימוק
מפורש לאי-הצגה — ⛔ אין שדה בלי אחד משניהם.** המיפוי הזה עצמו חשף פער
שלא נתפס ב-checkpoint 1: ל-`base_rate` לא היה רכיב כלל — תוקן ב-§1.1.

### 5.1 — `LtvPrediction` (P2)

| שדה | טיפוס/אילוץ | רכיב מוצג / נימוק אי-הצגה |
|---|---|---|
| `point_estimate` | `float \| None` | `prediction-primary` |
| `lower_bound` · `upper_bound` | `float \| None` | `prediction-range` |
| `interval_method` | `Literal["split_conformal"]` | `model-details` |
| `interval_details.nominal_coverage` · `.measured_coverage` | `float` | `model-details` |
| `evidence_level` | `Literal["low"] \| None` | `evidence-badge` |
| `in_training_domain` | `bool` | ⛔ לא ערך מוצג — קובע אם `prediction-panel` במצב רגיל או `ood-banner` (invariant דו-כיווני מול `warnings`) |
| `warnings[OODWarning]` | `list` | `ood-banner` — `message`/`feature`/`min`/`max` מהאזהרה |
| `warnings[UnobservedBudgetWarning]` | `list` | הודעת `evidence-badge` (§1.1) |
| `model_version` · `model_algorithm` | `str` | `model-details` |
| `metrics.cv.mean_mae` · `metrics.cv.mean_rmse` · `metrics.cv.mean_r2` | `float` | `model-details` |
| `metrics.holdout.mae` · `metrics.holdout.rmse` · `metrics.holdout.r2` | `float` | `model-details` |

### 5.2 — `PropensityPrediction` (P3, P4 — סכמה משותפת)

| שדה | טיפוס/אילוץ | רכיב מוצג / נימוק אי-הצגה |
|---|---|---|
| `event_probability` | `float \| None` | `prediction-primary` (כאחוזים, F1) |
| `base_rate` | `float` | `base-rate-line` |
| `propensity_band` | `Literal[...] \| None` | `propensity-band-badge` |
| `evidence_level` | `Literal["low"] \| None` | `evidence-badge` |
| `in_training_domain` | `bool` | ⛔ קובע מצב `ood-banner`, כמו P2 |
| `warnings[OODWarning]` | `list` | `ood-banner` |
| `warnings[UnobservedBudgetWarning]` | `list` | הודעת `evidence-badge` |
| `model_version` · `model_algorithm` | `str` | `model-details` |
| `calibration_status` | `Literal["calibrated","uncalibrated"]` | `calibration-badge` |
| `calibration_method` | `Literal["sigmoid"]` | `model-details` |
| `metrics.cv.mean_roc_auc` · `metrics.cv.mean_pr_auc` · `metrics.cv.mean_brier` · `metrics.cv.mean_log_loss` | `float` | `model-details` |
| `metrics.holdout.roc_auc` · `metrics.holdout.pr_auc` · `metrics.holdout.brier` · `metrics.holdout.log_loss` | `float` | `model-details` |

### 5.3 — `SuperCustomerPrediction` (P4S)

| שדה | טיפוס/אילוץ | רכיב מוצג / נימוק אי-הצגה |
|---|---|---|
| `event_probability` | `float \| None` | `prediction-primary` (מומר למספר שלם 0–100; כלל ההמרה בפאזה 11, `PHASE8A.md` D15ב) |
| `base_rate` | `float` | `base-rate-line` |
| `propensity_band` | `Literal[...] \| None` | `propensity-band-badge` |
| `evidence_level` | `Literal["low"] \| None` | `evidence-badge` |
| `in_training_domain` | `bool` | ⛔ קובע מצב `ood-banner` וריאנט P4S (§2.3) |
| `warnings[SuperCustomerOODWarning]` | `list` | `ood-banner` וריאנט P4S — ארבעה פיצ'רים בלבד |
| `warnings[UnobservedBudgetWarning]` | `list` | הודעת `evidence-badge` |
| `model_version` · `model_algorithm` | `str` | `model-details` |
| `calibration_status` | `Literal["calibrated"]` | `calibration-badge` — **נעול**, ⛔ `uncalibrated` לא אפשרי כאן |
| `calibration_method` | `Literal["sigmoid"]` | `model-details` |
| `metrics.cv.mean_roc_auc` · `metrics.cv.mean_pr_auc` · `metrics.cv.mean_brier` · `metrics.cv.mean_log_loss` | `float` | `model-details` |
| `metrics.holdout.roc_auc` · `metrics.holdout.pr_auc` · `metrics.holdout.brier` · `metrics.holdout.log_loss` | `float` | `model-details` |
| `target_definition` | `Literal["referred=Yes AND upsell=1 AND ltv_months>=34"]` | **גלוי בגוף `prediction-panel` וריאנט P4S**, ⛔ לא ב-`model-details` (`IA.md` §3א.4 — "הגדרות גלויות") |
| `population_definition` | `Literal["purchased=1"]` | כנ"ל — גלוי, לא ב-`model-details` |

### 5.4 — `BudgetAllocation` · `StrategyResult` · `BudgetSimulation` (P6)

⚠ `BudgetSimulation.strategies` (`list[StrategyResult]`) ו-
`StrategyResult.allocations` (`list[BudgetAllocation]`) הם **שדות מיכל**
— פורקו לשדותיהם המקוננים בטבלה שלמטה ולא קיבלו שורה עצמאית משלהם;
המיכל עצמו אינו ערך מוצג בפני עצמו.

| שדה | טיפוס/אילוץ | רכיב מוצג / נימוק אי-הצגה |
|---|---|---|
| `BudgetAllocation.ad_budget` · `.count` | `int` | `strategy-row` — פירוט ההקצאה |
| `BudgetAllocation.sample_size` | `int` | `strategy-row` — `n` לכל רמה |
| `StrategyResult.strategy_id` | `Literal[4 ערכים]` | `strategy-row` — שם האסטרטגיה |
| `StrategyResult.rank` | `int` | `strategy-row` — מיקום בדירוג |
| `StrategyResult.point_estimate` | `float` | `strategy-row` — רווח צפוי |
| `StrategyResult.lower_bound` · `.upper_bound` | `float` | `strategy-row` — whisker |
| `StrategyResult.bootstrap_iterations` | `int` | `model-details` |
| `StrategyResult.evidence_level` | `Literal["high","medium","low"]` | `evidence-badge` |
| `StrategyResult.in_training_domain` | `Literal[True]` | ⛔ **קבוע, אינו מייצר מצב תצוגה** — `ood-banner` אינו נגיש כאן מבנית (`IA.md` §6.1, §2.2) |
| `StrategyResult.warnings` | `list`, `max_length=0` | ⛔ **תמיד ריק בפועל** (אילוץ סכמה) — אין רכיב אזהרה בסימולטור |
| `BudgetSimulation.total_budget` | `Literal[50000]` | כותרת המסך — `₪50,000` |
| `BudgetSimulation.interval_method` · `.bootstrap_percentiles` | `Literal[...]` | `model-details` |
| `BudgetSimulation.top_two_overlap` | `bool` | `overlap-alert` |
| `BudgetSimulation.model_version` · `.model_algorithm` | `str` | `model-details` |
| `BudgetSimulation.metrics.cv.mean_mae` · `BudgetSimulation.metrics.cv.mean_rmse` · `BudgetSimulation.metrics.cv.mean_r2` | `float` | `model-details` |
| `BudgetSimulation.metrics.holdout.mae` · `BudgetSimulation.metrics.holdout.rmse` · `BudgetSimulation.metrics.holdout.r2` | `float` | `model-details` |

✅ כל שדה בארבע הסכמות (`LtvPrediction`, `PropensityPrediction`,
`SuperCustomerPrediction`, `BudgetSimulation`+`StrategyResult`+
`BudgetAllocation`) מקבל רכיב מוצג או נימוק מפורש. `warnings` בכל
הסכמות מפורק **לפי סוג האזהרה בפועל** (`OODWarning`/`SuperCustomerOODWarning`
מול `UnobservedBudgetWarning`), ⛔ לא מוצג כרשימה גולמית.

## 6. סיכום והמלצה (D9, checkpoint 6)

מטריצת D9 (מקור: `PHASE10.md` D9) מספקת לכל פאנל תוצאה וכל גרף עסקי תשובה
ברורה לאדם שאינו בקיא בסטטיסטיקה, בארבע שכבות: **התשובה** · **מה זה
אומר** · **מה כדאי לעשות** · **חשוב לדעת**. ⚠ **שפת המשתמש**: ארבעת
העמודות המקבילות במטריצה (תשובה/משמעות/פעולה/מגבלה) הן משפט אחד או שניים
בעברית פשוטה, ⛔ בלי שמות שדות, נוסחאות או מונחי מימוש — אלה עוברים
לעמודת מקור הראיה או ל-§6.3. ⚠ **⛔ אין רשימת לקוחות**: ה-API והממשק
מחזירים תחזית ללקוח היחיד שנבדק, ⛔ לא רשימה או דירוג של לקוחות (החלטה
נעולה) — כל פעולה במטריצה מנוסחת על הלקוח הנוכחי, וכשהתחזית סביב שיעור
הבסיס או מתחתיו, ⛔ אין להמליץ על פעולה מיוחדת על בסיס המודל בלבד.

ההמלצות **דטרמיניסטיות** ומשלבות רק שני סוגי מקור מתועדים: שדות מתגובת
הבקשה הנוכחית ועובדות קבועות מנכס תצוגה גרסאי. עובדה קבועה אינה מוצגת
כמדידה חדשה, וטקסט כללי אינו מוצג כהמלצה אישית. ⛔ אין AI בזמן ריצה ·
⛔ אין טענה סיבתית · ⛔ אין הבטחת תוצאה · כשהראיות חלשות — אומרים במפורש
שאין המלצה חד-משמעית ומציעים בדיקה ידנית, איסוף נתונים או ניסוי מבוקר.

⚠ **שני יעדים מתוך השמונה הם יכולות משלימות**, ובכל זאת חייבים שורה — D9
חל על כל פאנל תוצאה וכל גרף. `P4` הוא חיזוי הפניה משלים בתוך הטופס המשותף
ו־`calls_to_closed` הוא הגרף השני ב־Follow-up. חמש דרישות המקור נגישות
בנפרד דרך `capability-index` (§1.4, קריטריון 24), בלי לחשוף במוצר את זהות
המייסדת, קודי המשימות או רשומות העבודה הפנימיות.

### 6.1 — מטריצת שש העמודות

⚠ **בתא הראשון (שאלה/יעד) בלבד, כל שורה נושאת מזהה חד-משמעי לאחד משמונת
היעדים הנעולים** (`PHASE10.md` D9: Overview · P2 · P3 · P4 · P4S · Budget
Simulator · שני גרפי Follow-up — נשירה ו-`calls_to_closed`), **בדיוק פעם
אחת לכל יעד** — כך שבדיקה 9 (`test_design_tokens.py`) מזהה כל שורה
מכנית. חמשת התאים האחרים רשאים להזכיר יעדים אחרים בחופשיות (למשל תשובת
Overview שמפנה ל-P2, או הבחנת P4/P4S זו מזו) — הזיהוי בודק את תא השאלה
בלבד, לא את השורה כולה.

| שאלת המקור / יעד משלים | תשובה פשוטה | משמעות עסקית | פעולה מומלצת | מגבלה | מקור ראיה ומימוש |
|---|---|---|---|---|---|
| **Overview** — איזו רמת הוצאת פרסום חודשית ממירה הכי טוב, והאם זה מפתיע? | {הרמה בעלת שיעור ההמרה הגבוה בתגובה, או שוויון} — {השיעורים שחזרו} | אם רצף Low→Mid→High אינו עולה, הוצאה גבוהה יותר לא הניבה המרה גבוהה יותר — ממצא מפתיע ביחס לציפייה הפשוטה; אחרת אין לטעון להפתעה | להשוות את רמת ההוצאה הנוכחית לטבלה לפני שמזיזים כסף, ולבחון את החלופות בסימולטור | ההשוואה מתארת קבוצות בנתונים ההיסטוריים ואינה מוכיחה שהזזת תקציב תשנה את ההמרה | **בקשה נוכחית—Supabase:** `BudgetTiersResponse.tiers[].budget_tier`, `.conversion_rate`, `.n_records` מ־`GET /api/insights/budget-tiers` ← `budget_tier_insight`; המקסימום נבחר רק משורות Low/Mid/High בעלות שיעור, ושוויון נשמר |
| **P2** — כמה זמן צפוי לקוח חדש להישאר? | תחזית: {X} חודשים, טווח: {Y}–{Z} חודשים | הערכה לאורך החיים הכולל של לקוח שנרכש בקמפיין שהסתיים. במודלים שאומנו על הנתונים ההיסטוריים, מספר השיחות הממוצע עד סגירה היה האות החזק ביותר, אך אינו מוכיח שיותר שיחות מאריכות קשר | כשהקלט בתחום ואינו מסומן בתמיכה חלקית, להשתמש באומדן בזהירות לתכנון ופילוח; לבחון שינוי במדיניות השיחות רק בניסוי שמודד שימור בפועל | זהו טווח אי־ודאות, לא הבטחה. ב־OOD אין תחזית; בתמיכה חלקית אין החלטת פילוח לפי המודל בלבד | **בקשה נוכחית—API:** `LtvPrediction.point_estimate`, `.lower_bound`, `.upper_bound`, `.in_training_domain`, `.warnings[]`, `.evidence_level`; פרטים: `.interval_method`, `.interval_details.nominal_coverage`, `.interval_details.measured_coverage`, `.metrics.cv.mean_mae`, `.metrics.cv.mean_rmse`, `.metrics.cv.mean_r2`, `.metrics.holdout.mae`, `.metrics.holdout.rmse`, `.metrics.holdout.r2`, `.model_version`, `.model_algorithm`. **קבוע—נכס תצוגה:** `ltv.rank_1_by_algorithm.*` ו־`ltv.dominant_feature`, נגזרים מ־`metrics.json.global_feature_importance.P2` |
| **P3** — מי צפוי לקנות יותר? | נטייה לאפסייל: {X}%, {N} נקודות מעל/מתחת לשיעור הבסיס | התוצאה מציבה את התרחיש מעל, סביב או מתחת לשיעור האפסייל שנמדד באוכלוסיית האימון | רק כשהקלט בתחום, התוצאה מכוילת, אין סימון תמיכה חלקית והנטייה מעל הבסיס, אפשר לשקול פנייה אחרי בדיקה ידנית. בכל מצב אחר אין פעולה מיוחדת לפי המודל | כשהתוצאה מכוילת, זהו אומדן הסתברותי מנתוני סוף קמפיין; אם אינה מכוילת, אין לפרש אותה כהסתברות ואין לפעול לפיה. אין הבטחה או השפעה סיבתית | **בקשה נוכחית—API:** `PropensityPrediction.event_probability`, `.base_rate`, `.propensity_band`, `.in_training_domain`, `.warnings[]`, `.evidence_level`; ההפרש הוא `event_probability-base_rate`; פרטים: `.calibration_status`, `.calibration_method`, `.metrics.cv.mean_roc_auc`, `.metrics.cv.mean_pr_auc`, `.metrics.cv.mean_brier`, `.metrics.cv.mean_log_loss`, `.metrics.holdout.roc_auc`, `.metrics.holdout.pr_auc`, `.metrics.holdout.brier`, `.metrics.holdout.log_loss`, `.model_version`, `.model_algorithm` |
| **P4** — מה הסיכוי שהלקוח יפנה לקוחות נוספים? (יכולת משלימה) | נטייה להפניה: {X}%, מול שיעור הבסיס שחזר | התוצאה מציבה את התרחיש מעל, סביב או מתחת לשיעור ההפניה שנמדד באוכלוסיית האימון. ציון לקוח-על מוצג במסך נפרד | רק כשהקלט בתחום, התוצאה מכוילת, אין סימון תמיכה חלקית והנטייה מעל הבסיס, אפשר לשקול בקשת הפניה אחרי בדיקה ידנית. בכל מצב אחר אין פעולה מיוחדת לפי המודל | אם התוצאה אינה מכוילת, אין לפרש אותה כהסתברות ואין לפעול לפיה. גם אומדן מכויל אינו הבטחה או השפעה סיבתית; זהו חיזוי הפניה בלבד, ⛔ לא ציון לקוח-על | **בקשה נוכחית—API:** `PropensityPrediction.event_probability`, `.base_rate`, `.propensity_band`, `.in_training_domain`, `.warnings[]`, `.evidence_level`, `.calibration_status`, `.calibration_method`, `.metrics.cv.mean_roc_auc`, `.metrics.cv.mean_pr_auc`, `.metrics.cv.mean_brier`, `.metrics.cv.mean_log_loss`, `.metrics.holdout.roc_auc`, `.metrics.holdout.pr_auc`, `.metrics.holdout.brier`, `.metrics.holdout.log_loss`, `.model_version`, `.model_algorithm` מ־`POST /api/predict/referral`; אין מדד נוסף ממקור קבוע |
| **P4S** — מי מבין הרוכשים עשוי להפוך ללקוח-על? | ציון לקוח-על: {X} מתוך 100, מול שיעור הבסיס שחזר | היסטורית, לקוחות-על היו {אחוז} מהרוכשים, יצרו {אחוז} מהרווח המצטבר; עלות הרכישה הממוצעת שלהם הייתה {עלות}, לעומת {עלות באוכלוסיית הרוכשים}, כלומר נמוכה ב־{אחוז}. זהו פרופיל תיאורי | רק כשהקלט בתחום, אין סימון תמיכה חלקית והנטייה מעל הבסיס, אפשר להשתמש בציון כאות מסייע לבדיקה ידנית של רוכש ידוע. בכל מצב אחר אין תעדוף לפי המודל | תקף רק אחרי רכישה ידועה, מעקב 1 וחלון חודשי סגור. CatBoost נמדד ב־Holdout עם ROC-AUC ‏0.8014 ו־PR-AUC ‏0.3420, אך Recall ‏0 בסף ברירת המחדל; לכן הציון הוא אות מסייע בלבד | **בקשה נוכחית—API:** `SuperCustomerPrediction.event_probability`, `.base_rate`, `.propensity_band`, `.evidence_level`, `.in_training_domain`, `.warnings[]`, `.calibration_status`, `.calibration_method`, `.metrics.cv.mean_roc_auc`, `.metrics.cv.mean_pr_auc`, `.metrics.cv.mean_brier`, `.metrics.cv.mean_log_loss`, `.metrics.holdout.roc_auc`, `.metrics.holdout.pr_auc`, `.metrics.holdout.brier`, `.metrics.holdout.log_loss`, `.model_version`, `.model_algorithm`, `.target_definition`, `.population_definition`; **קבוע—נכס תצוגה:** `super_customer_profile.pct_of_purchased`, `.pct_of_total_profit`, `.cac_super_mean`, `.cac_population_mean`, `.cac_savings_pct` מ־`app/static/business_facts.json`. המודל הפעיל הוא CatBoost בגרסה `P4S-catboost-20260912-1c70ca8` |
| **Budget Simulator** — לאן להקצות את תקציב הפרסום? | `100x500` מדורגת ראשונה מספרית, אך אינה המלצה לפעולה; שתי המובילות חופפות ובדיקת העבר של רמת 500 חלשה מאוד | הדירוג לבדו אינו מכריע: טווחי `100x500` ו־`25x2000` חופפים, ובבדיקת עבר התחזית לרמת 500 הייתה גבוהה פי 8.59 מהתוצאה בפועל | לא לבצע הקצאה מלאה לפי הדירוג. אם בוחנים אחת מארבע החלופות, לבצע פיילוט מבוקר של `25x2000`, שלה 322 שורות אימון ובדיקת עבר קרובה יותר | הסכומים הם רווח מצטבר צפוי ומניחים רשומות עצמאיות ואדיטיביות; אינם רווח בחודש הבא, אינם השפעה סיבתית ואינם הבטחה | **בקשה נוכחית—API כלוקאפ קבוע מראש:** `BudgetSimulation.total_budget`, `.interval_method`, `.bootstrap_percentiles`, `.top_two_overlap`, `.strategies[].strategy_id`, `.strategies[].rank`, `.strategies[].allocations[].ad_budget`, `.strategies[].allocations[].count`, `.strategies[].allocations[].sample_size`, `.strategies[].point_estimate`, `.strategies[].lower_bound`, `.strategies[].upper_bound`, `.strategies[].bootstrap_iterations`, `.strategies[].evidence_level`, `.model_version`, `.model_algorithm`, `.metrics.cv.mean_mae`, `.metrics.cv.mean_rmse`, `.metrics.cv.mean_r2`, `.metrics.holdout.mae`, `.metrics.holdout.rmse`, `.metrics.holdout.r2`; `GET /api/simulate/budget` ללא body. הפרופילים נגזרים משורות train שנצפו, ו־`profile_source_row_id` נשמר לכל רמה |
| **נשירה** (Follow-up) — באיזה שלב הנשירה מתנהגת באופן לא צפוי? | שיעורי הנשירה הם {חמשת השיעורים שחזרו}; {השלב בעל השיעור הנמוך ביותר} הוא הנמוך | אם השיעורים אינם עולים ברצף, הנתונים אינם תומכים בעצירה אוטומטית רק מפני שהתקדם מספר השלב | ההמלצה היא להמשיך מעקבים אחרי השלישי באופן מבוקר ולמדוד בכל שלב את שיעור הסגירה השולי, זמן העבודה והעלות לפני שינוי קבוע במדיניות | הנתונים מתארים מה קרה בפועל בכל שלב, ⛔ ואינם מסבירים מדוע | **בקשה נוכחית—Supabase:** `FollowupResponse.stages.status`; בהצלחה `.data[].stage_order`, `.stage`, `.from_leads`, `.to_leads`, `.drop_rate` מ־`followup_insight`; בכשל `.error.reason_code`, `.error.message`. אין החלפה במספר שמור |
| **calls_to_closed** (Follow-up) — עבור עסקאות שנסגרו, כמה מעקבים הן דרשו בדרך כלל? | אין בקובץ מניין מעקבים לעסקה בודדת. במדד הקרוב, `calls_to_closed`, ב־{population_n} רשומות שנסגרו: חציון {median}, שכיח {mode} וממוצע {mean} | ב־{count_ge_4} רשומות ({rate_ge_4}) ממוצע השיחות עד סגירה הוא 4 ומעלה. יחד עם דפוס הנשירה, אין בסיס לעצירה אוטומטית אחרי המעקב השלישי | ההמלצה היא להמשיך מעקבים אחרי השלישי באופן מבוקר ולמדוד בכל שלב את שיעור הסגירה השולי, זמן העבודה והעלות לפני שינוי קבוע במדיניות | `calls_to_closed` הוא ממוצע ברמת רשומה ולא היסטוריה לעסקה; חמשת שלבי המעקב אינם מספר השיחות, שמגיע עד 9; אין הוכחה סיבתית או כלכלית | **בקשה נוכחית—Supabase + נגזרת דפדפן:** `FollowupResponse.calls_to_closed.status`; בהצלחה `.data.population_n`, `.data.distribution[].calls`, `.data.distribution[].n`; בכשל `.error.reason_code`, `.error.message`; ארבעת הסיכומים נגזרים מאותה התפלגות בלבד. השרת מסנן `closed>0`, קורא את כל העמודים ומשווה לספירה עצמאית על אותו מסנן |

> **תיקון CP9 הושלם:** `docs/FINDINGS.md`, ‏`docs/findings.json` וה־endpoint
> משתמשים כולם באוכלוסיית `closed>0` ‏(3,318 רשומות). פיצול
> `closed=1`/`closed>=2` ‏(5.653/3.353) נשמר כהקשר משני בלבד; הוא אינו
> מחליף את הנתון הטיפוסי לכל `closed>0`.

#### 6.1א — חוזה המקורות והחישובים הפנימי

סימון המקור בעמודה האחרונה אינו טקסט מוצר. `בקשה נוכחית—API` ו־
`בקשה נוכחית—Supabase` פירושם שהמספר מתקבל בעקבות פתיחת המסך או שליחת
הטופס עבור **דור הקלט הנוכחי**. ה־CSV הוא snapshot סופי וקפוא של מטלת
הקורס ולעולם לא יקבל נתונים חדשים. האינטראקטיביות היא חישוב תחזית או
הצגת תוצאה בתגובה לפעולת המשתמש על בסיס אותו snapshot; היא אינה רענון נתונים.
הקריאה דרך API ו־Supabase מוכיחה שהחיווט, Auth, JWT ו־RLS עובדים.
`קבוע—נכס תצוגה` פירושו עובדה היסטורית שמקורה, גרסתה וגיבוב המקור שלה
נרשמו בזמן הבנייה. נוסח פעולה הוא תבנית קבועה שמקבלת רק ערכים משני
המקורות האלה.

ארבעת נתיבי ה־POST מקבלים בדיוק את סדר וסוגי הקלט שב־meta ובסכמה:

| נתיבים | סכמה וסדר מחייב | התאמה לפני מימוש |
|---|---|---|
| `ltv` · `upsell` · `referral` | `FunnelInput`: ‏`ad_budget`, `num_leads`, `leads_answered`, `followup_1`, `followup_2`, `followup_3`, `followup_4`, `followup_5`, `not_closed`, `closed`, `calls_to_closed`, `calls_to_not_closed`, `customer_acquisition_cost`; כולם `strict int` אי־שליליים | השמות והסדר חייבים להיות זהים ל־`models/P{2,3,4}.meta.json.feature_columns`; אין שדה עסקי נוסף |
| `super-customer` | `EarlyFunnelInput`: ‏`ad_budget`, `num_leads`, `leads_answered`, `followup_1`; כולם `strict int` אי־שליליים | זהים ל־`models/P4S.meta.json.feature_columns`; אישור הרכישה/הזמן אינו פיצ'ר חמישי |

סיבות OOD מוצגות רק מ־`warnings[]` של אותה תגובה: `feature`, `value`,
`min`, `max`; הגבולות מגיעים מ־`*.meta.json.ood_bounds`. אם
`in_training_domain=false`, שדות התחזית הרלוונטיים הם `null` ואין לבנות
מספר חלופי. `model_version`, `model_algorithm` ובלוק `metrics` מגיעים
מהתגובה בלבד; הדפדפן אינו פותח את `models/`.

כללי המעבר מתגובה לטקסט הם חלק מהחוזה, כדי שתבנית קבועה לא תהפוך בטעות
להמלצה אישית שאינה נתמכת:

| יעד | תנאי תגובה | טקסט/פעולה מותרים |
|---|---|---|
| Overview | בוחנים רק שורות עם `budget_tier` בשם ו־`conversion_rate` שאינו `null`; שורת gap נשארת בטבלה אך אינה מועמדת ל"רמה הטובה" | מקסימום יחיד ⇒ מציגים אותו; שוויון ⇒ מציגים שוויון, בלי מנצחת. "מפתיע" מותר רק אם רצף Low→Mid→High הקיים אינו עולה באופן מונוטוני; אחרת אין לטעון להפתעה |
| P2 | `in_training_domain=false` | אין מספר ואין פעולה המבוססת על תחזית; מציגים את שדות ה־OOD ומבקשים לבדוק את הקלט |
| P2 | `in_training_domain=true` ו־`evidence_level="low"` | המספר והטווח מוצגים עם תמיכה חלקית; אין החלטת פילוח על בסיסם בלבד |
| P3/P4 | OOD, או `calibration_status="uncalibrated"`, או `evidence_level="low"` | אין המלצת פנייה אישית. ב־OOD אין מספר; במצב uncalibrated אין לכנות את הערך "הסתברות מכוילת" |
| P3/P4 | בתחום, מכויל, ללא סימון `low`, ו־`propensity_band="above_base"` | מותר להציע בדיקה ידנית לפני פנייה. ב־`near_base` או `below_base` אין פעולה מיוחדת לפי המודל |
| P4S | OOD או `evidence_level="low"` | אין תעדוף; ב־OOD אין ציון. `calibration_status` תמיד `calibrated` בחוזה |
| P4S | בתחום, ללא סימון `low`, ו־`propensity_band="above_base"` | הציון הוא אות מסייע לבדיקה ידנית בלבד; בשתי הקטגוריות האחרות אין פעולה מיוחדת |
| Budget Simulator | `top_two_overlap=true` | אין מנצחת חד־משמעית. וטו בדיקת העבר על `100x500` גובר על הדירוג ועל החפיפה; רק פיילוט מוגבל בדפוס `25x2000` מוצע. גם אם החפיפה `false`, rank 1 אינו אישור להקצאה מלאה |
| Follow-up | אחד משני החלקים `status="unavailable"` | מציגים רק את החלק התקין; ההמלצה המשולבת אינה זמינה ואין fallback קבוע |

שגיאת HTTP נקבעת מקוד הסטטוס, לא מטקסט: 401 מוביל להתחברות, 403 למסך
חוסר הרשאה, ו־500/503 לשגיאה עם ניסיון חוזר. בפלט חלקי של Follow-up המקור
המדויק הוא `stages.error.reason_code/message` או
`calls_to_closed.error.reason_code/message`; אפס שורות ב־Overview אינו
שיעור אפס אלא שגיאת זמינות. הודעות למשתמש מתורגמות ואינן חושפות טקסט שרת
גולמי.

ארבעת סיכומי `calls_to_closed` נגזרים רק לאחר
`calls_to_closed.status="available"`: הממוצע הוא
`sum(calls*n)/population_n`; ספירת 4+ היא `sum(n where calls>=4)` והשיעור
הוא הספירה חלקי `population_n`; החציון מחושב לפי שתי עמדות האמצע בהתפלגות
המשוקללת; השכיח הוא כל ערך בעל `n` מרבי, ובשוויון מוצגים כל הערכים.
הנגזרות אינן נשמרות כעובדות נפרדות ואינן מחושבות מפלט חלקי.

נכס התצוגה שנבנה ב־CP9 וייטען בפאזה 11 הוא
`app/static/business_facts.json`, קטן וללא שורות לקוח. הוא מכיל
`schema_version`, ‏`source_csv_sha256`, ‏`metrics_sha256`, ‏`model_versions`,
‏`source_keys`
ואת המפתחות הבאים בלבד:

- `ltv.rank_1_by_algorithm.catboost`, `.lightgbm`, `.xgboost`, נגזרים
  בנפרד מ־`models/metrics.json` → `global_feature_importance.P2`;
  `ltv.dominant_feature` נכתב רק אם שלושתם זהים. כך הטענה "שלושת המודלים
  מסכימים" ניתנת לבדיקה ואינה נשענת על שם יחיד שהועתק.
- `super_customer_profile.n_purchased`, `.n_super`,
  `.pct_of_purchased`, `.pct_of_total_profit`, `.cac_super_mean`,
  `.cac_population_mean`, `.cac_savings_pct`, `.population_definition`, נגזרים מ־
  `models/metrics.json` → `super_customer_profile`.
- `followup_context.mean_calls_closed_eq_1` ו־
  `.mean_calls_closed_ge_2` לצד `.population_definition="closed>0"`,
  נגזרים מחדש ב־CP9 ונועדו רק להסבר משני מתקפל; הם אינם התשובה הטיפוסית
  ואינם fallback לכשל בבקשה הנוכחית.

- **תיקון CP10:** `budget_backtest.500` ו־`budget_backtest.2000` מכילים רק
  `predicted_per_customer`, `actual_mean_per_customer`, `n_train_at_level`
  ו־`n_holdout_at_level` מתוך `models/metrics.json.P6_backtest` הקפוא.
  יחס ההערכת־יתר בתשובת D9 נגזר מחלוקת התחזית בממוצע בפועל (8.59 לאחר
  עיגול ברמת 500); אין בו קריאה חדשה ל־Holdout. אימות build מול `metrics_sha256`
  והתאמת `model_versions.P6` לגרסת התגובה נדרשים לפני חיבור ההסבר לתגובה; הדפדפן אינו קורא metrics. בכשל טעינת הנכס או אי־התאמה,
  טבלת הסימולציה התקינה נשארת אך המלצת התקציב והמספר 8.59 אינם מוצגים;
  אין להחליפם בהמלצה לפי rank בלבד. מזהי שורות אינם מועתקים לנכס.

הנכס נטען ומרונדר רק לאחר session תקין, אך הוא מכיל אגרגטים לא־רגישים
ואינו מנגנון הרשאה. אין לפרסם את כל `metrics.json`, את `findings.json`,
SVG של SHAP או שורת מקור כדי להציג את העובדות המצומצמות האלה.

#### 6.1ב — ביטול תוכן אישי ישן

שינוי קלט, החלפת דוגמה, יציאה או תחילת בקשה חדשה מבטלים מיד תשובה אישית
והמלצה שתלויה בה. תגובה מאוחרת מדור ישן אינה מרונדרת. טקסט הסבר כללי
ועובדה היסטורית מסומנת רשאים להישאר, אך בלי מספר החיזוי הישן ובלי פעולה
שמנוסחת כאילו היא שייכת לקלט החדש. בכשל חלקי ב־Follow-up אין מסקנה
משולבת ואין fallback מהנכס הקבוע.

### 6.2 — מסקנת Follow-up המלאה (מקור: `SPEC.md` § הכרעת CP4-D)

⚠ **הפסקה הבאה מצוטטת מילה במילה מ-`SPEC.md`, במלואה, פעם אחת בלבד** —
כבלוק ברמת המסך ב-Follow-up, ⛔ לא משוכפלת ליד כל אחד משני הגרפים ו⛔ לא
מקוצרת. שתי שורות §6.1 (נשירה, `calls_to_closed`) נושאות רק את משפט
הפעולה המשותף; המשמעות והמגבלה בהן ייחודיות לכל גרף. הפניה ל-§3.4: בשורת
Follow-up, בלוק זה יושב ברוחב מלא מתחת לשתי קבוצות הפריסה — ⛔ לא כעמודה
שלישית ו⛔ לא בתוך קבוצה.

> **לא. אין לאמץ עצירה אוטומטית אחרי המעקב השלישי.** שיעור הנשירה לאחר המעקב
> הרביעי הוא הנמוך בשרשרת (10.4%). מבין 3,318 הרשומות שבהן נסגרה עסקה
> (`closed>0`), הקובץ אינו מאפשר למנות סבבי מעקב לעסקה בודדת. במדד הקרוב,
> התפלגות `calls_to_closed` ברמת הרשומה, החציון הוא 3, הערך
> השכיח הוא 2 והממוצע 3.706; ב־1,595 רשומות (48.07%) הממוצע הוא 4 שיחות ומעלה.
> חמשת שלבי המעקב מתארים כמה לידים נותרו אחרי כל סבב, ואילו
> `calls_to_closed` הוא ממוצע שיחות ברמת רשומה שיכול להגיע עד 9. לכן אי אפשר
> לומר ש־48.07% מהעסקאות הבודדות דרשו 4+ שיחות, או שהשיחות המאוחרות גרמו
> לסגירה. ההמלצה היא להמשיך מעקבים אחרי השלישי באופן מבוקר ולמדוד בכל שלב
> את שיעור הסגירה השולי, זמן העבודה והעלות לפני שינוי קבוע במדיניות.

בכשל של אחד משני מקורות הנתונים מציגים רק את החלק התקין ומסמנים את ההמלצה
המשולבת כלא זמינה. אין להשתמש במספרים היסטוריים שמורים כתחליף לתוצאה חסרה בבקשה הנוכחית.

### 6.3 — הערות מימוש (למפתח, לא למשתמש)

⚠ **מעמד הסעיף:** מקור פנימי לפאזה 11, ⛔ ואינו טקסט מוצג למשתמש. ⛔ **אין
להסיק שכל הערה טכנית כאן מגיעה ל"פרטי המודל"** — ל-`model-details` רשאים
להגיע **רק שדות הקיימים בחוזה החי** (`app/schemas.py`, ומוצגים לפי §5);
הערה שאין לה שדה תואם בחוזה נשארת כאן בלבד. תקדים: `B32` (Accuracy,
Precision, Recall, F1, ROC-AUC) נשאר ב-`REPORT.md` בלבד מפני שארבעה
מחמשת המדדים שהוא דורש אינם קיימים בחוזה כלל — `_CvClassification`/
`_HoldoutClassification` נושאים רק `roc_auc`/`pr_auc`/`brier`/`log_loss`.

| יעד | הערות |
|---|---|
| Overview | `gap (1501–1999)` מוצג כשורה נפרדת בטבלה; טייר בלי רשומות אינו מחזיר שורה כלל; `conversion_rate` ריק ⇒ N/A, ⛔ לא אפס (§2.1) |
| P2 | הטווח מ-`split_conformal` עם קוונטיל קבוע לכל הרשומות וחיתוך באפס; `evidence_level` מתאר תמיכת קלט בלבד ואינו משנה את הטווח. דומיננטיות `calls_to_closed`: אומתה ב-`models/metrics.json` → `global_feature_importance.P2` (catboost 96.0 מתוך כ-100, lightgbm 317 מול 200 בפיצ'ר הבא, xgboost 0.97 מתוך כ-1.0). ⚠ **B29c** ("strongest lever on customer longevity") נשאר `gap` בבעלות פאזה 13 (`REQUIREMENTS.md`); פאזה 10 תורמת חזותית בלבד ⛔ ואינה סוגרת |
| P3, P4 | כיול `sigmoid`; ספי הקטגוריה `0.9×`/`1.1× base_rate` = 41.715%/50.985% ל-P3, 38.439%/46.981% ל-P4 (`IA.md` §4) — מוסכמת תצוגה מפאזה 7, ⛔ לא ממצא סטטיסטי. `calibration_status=uncalibrated` אפשרי ומוצג בשני הפאנלים (§2.4) |
| P4S | `target_definition = referred=Yes AND upsell=1 AND ltv_months>=34`, `population_definition = purchased=1` — גלויים בגוף הפאנל (§5.3), ⛔ לא ב-`model-details`. הקטגוריה מחושבת מול `event_probability` הגולמי, ⛔ לא מול הציון המעוגל (`IA.md` §4). OOD על ארבעה פיצ'רים בלבד מ-`models/P4S.meta.json` (§2.3). ⛔ אין טווח ואין `uncalibrated` במסך זה (§2.4, קריטריון 15); הציון ⛔ אינו נצבע `positive`/`negative` (§3.1, D10). פרופיל לקוחות-העל: `models/metrics.json` → `super_customer_profile` (529 מתוך 3,163 רוכשים) |
| Budget Simulator | `bootstrap_percentile`, `B=1,000`, אחוזוני 2.5/97.5; המודל הנפרס `LinearRegression`; הנחת אדיטיביות ⛔ ואי-סיבתיות; ⛔ אין extrapolation מחוץ ל-500–20,000 (`IA.md` §6). `in_training_domain` קבוע `true` ⇒ OOD אינו נגיש (§2.2). פרופיל כל רמת תקציב הוא שורת train רב־משתנית שנצפתה; `100x500` נשארת דירוג מספרי בלבד בגלל חפיפה ובדיקת עבר חלשה ברמת 500 |
| נשירה, `calls_to_closed` | שיעורי הנשירה הם יחס 0–1 מ-view `followup_insight`; אפס שורות = שגיאת זמינות, ⛔ לא "אין נשירה" (§2.1). ההתפלגות מסוננת ב־`closed>0`; רשומת `closed ≥ 2` נספרת כאחת. סכום התדירויות מאומת מול ספירה עצמאית על אותו מסנן, בעימוד מלא (`IA.md` §7.1) |

---

## 7. מפת שדות קלט (D11, checkpoint 6)

⚠ **17 מופעי קלט בממשק, אך 13 שמות טכניים ייחודיים בלבד** — ארבעת שדות
P4S חוזרים על שמות שכבר מופיעים בטופס המשותף (§7.1), אך **⛔ אין למזג את
השורות**: ההקשר ומועד המדידה שונים לגמרי, וזו בדיוק ההבחנה ש-D11 נועד
להבהיר (`PHASE10.md` D11). חמש עמודות בכל שורה: **תווית עסקית בעברית ·
שם טכני באנגלית · יחידה · מועד מדידה · הסבר קצר**.

### 7.1 — הטופס המשותף (13 ערכי חוזה, P2·P3·P4)

מועד המדידה זהה לכל 13 השדות: **תום מחזור הקמפיין שבו הלקוח נרכש**
(`SPEC.md` § נקודות חיזוי) — האגרגטים (`not_closed`, `calls_to_not_closed`,
עלות הרכישה הסופית ומספר העסקאות הסופי) אינם ידועים בזמן רכישה בודדת,
ונודעים רק כשהקמפיין נסגר.

| תווית עסקית | שם טכני | יחידה | מועד מדידה | הסבר קצר |
|---|---|---|---|---|
| רמת הוצאת פרסום חודשית | `ad_budget` | ש"ח לחודש | תום מחזור הקמפיין | כמה הוצא בפועל על פרסום בחודש, עבור קמפיין הלקוח |
| מספר הלידים שנוצרו | `num_leads` | לידים | תום מחזור הקמפיין | כמה פניות נוצרו בסך הכול בקמפיין |
| לידים שענו לטלפון | `leads_answered` | לידים | תום מחזור הקמפיין | מתוך הלידים שנוצרו, כמה ענו כשהתקשרו אליהם |
| לידים שנותרו אחרי מעקב 1 | `followup_1` | לידים | תום מחזור הקמפיין | כמה לידים עדיין פעילים במשפך אחרי סבב המעקב הראשון |
| לידים שנותרו אחרי מעקב 2 | `followup_2` | לידים | תום מחזור הקמפיין | כנ"ל, אחרי סבב המעקב השני |
| לידים שנותרו אחרי מעקב 3 | `followup_3` | לידים | תום מחזור הקמפיין | כנ"ל, אחרי סבב המעקב השלישי |
| לידים שנותרו אחרי מעקב 4 | `followup_4` | לידים | תום מחזור הקמפיין | כנ"ל, אחרי סבב המעקב הרביעי |
| לידים שנותרו אחרי מעקב 5 | `followup_5` | לידים | תום מחזור הקמפיין | כנ"ל, אחרי סבב המעקב החמישי — האחרון בשרשרת |
| לידים שלא הומרו | `not_closed` | לידים | תום מחזור הקמפיין | ערך לקריאה בלבד: לידים שנותרו אחרי מעקב 5 פחות עסקאות שנסגרו. מוצגים המקור והנוסחה; נשלח כחלק מ־13 ערכי החוזה |
| עסקאות שנסגרו | `closed` | עסקאות | תום מחזור הקמפיין | מספר העסקאות שנסגרו בפועל. ⚠ מונה **עסקאות**, ⛔ לא לידים — `closed + not_closed = followup_5` (כלל ולידציה, §2.5) משווה שתי יחידות ספירה שונות שסכומן מתאזן מבנית |
| ממוצע שיחות עד סגירה | `calls_to_closed` | שיחות (ממוצע) | תום מחזור הקמפיין | ממוצע מספר השיחות שנדרשו לפני שעסקה נסגרה. ⚠ ממוצע **ברמת רשומה**, ⛔ לא היסטוריה של עסקה בודדת |
| ממוצע שיחות עד ויתור | `calls_to_not_closed` | שיחות (ממוצע) | תום מחזור הקמפיין | ממוצע מספר השיחות עד שוויתרו על ליד שלא נסגר. ⚠ אותה הסתייגות — ממוצע, ⛔ לא היסטוריה פר-עסקה |
| עלות ממוצעת לרכישת לקוח | `customer_acquisition_cost` | ש"ח ללקוח | תום מחזור הקמפיין | עלות הרכישה הממוצעת לכל לקוח שנרכש בקמפיין |

### 7.2 — ציון לקוח-על מוקדם (4 שדות, P4S)

מועד השימוש זהה לארבעת השדות: **אחרי שהרכישה ידועה, מעקב 1 הושלם וחלון
הגיוס החודשי נסגר** (`SPEC.md` § נקודות חיזוי; `IA.md` §3א.3). הוא מוקדם
ביחס לתוצאות היעד של לקוח־על, ⛔ לא תחזית לפני רכישה. אין ב־CSV תאריכים,
ולכן `context-confirmation` מצהיר על תנאי השימוש ואינו הוכחת זמן מתוך הנתונים.

| תווית עסקית | שם טכני | יחידה | מועד מדידה | הסבר קצר |
|---|---|---|---|---|
| רמת הוצאת פרסום חודשית | `ad_budget` | ש"ח לחודש | רכישה ידועה, מעקב 1 הושלם וחלון חודשי נסגר | הוצאה בפועל בחלון החודשי הסגור שאליו משתייכת קבוצת הלידים |
| מספר הלידים שנוצרו | `num_leads` | לידים | אותו מועד שימוש | גודל קבוצת הגיוס החודשית לאחר סגירת החלון |
| לידים שענו לטלפון | `leads_answered` | לידים | אותו מועד שימוש | כמה מהלידים בקבוצה הסגורה ענו לטלפון |
| לידים שנותרו אחרי המעקב הראשון | `followup_1` | לידים | אותו מועד שימוש | האות המוקדם היחיד משרשרת המעקבים; מעקבים 2–5 ותוצאות היעד אינם קלט |

⚠ **⛔ אין להמציא יחידה או מועד מדידה** — כל 13 השדות מגובים במילון
העמודות של הבריף (`FunnelIQ_Assignment.html` § Data dictionary) ובמועד
המדידה הנעול ב-`SPEC.md` § נקודות חיזוי; שדה שיתגלה בעתיד בלי מקור
לאחת מחמש העמודות מחייב עצירה והעלאה כפער, ⛔ לא השלמה מהיגיון.

---

## 8. מסע המשתמש (B59, checkpoint 6)

שבעה שלבים, ברצף אחד ובניווט ברור (מקור: `PHASE10.md` §יג — פאזה 10
תורמת את המפרט החזותי ואת מסע המשתמש ל-B59, ⛔ ואינה סוגרת אותו; הראיה
למסע חי היא פאזה 12, ⛔ לא צילום מסך ולא מוקאפ):

| # | שלב | מסך |
|---|---|---|
| 1 | התחברות | Login |
| 2 | חמש יכולות עסקיות והפנייה לארבעת יעדי המוצר | Overview (§0, מסך 2) |
| 3 | ציון לקוח־על לרוכש ידוע — ארבעת שדות `EarlyFunnelInput` אחרי מעקב 1 ובחלון חודשי סגור | P4S (§0, מסך 4) |
| 4 | תחזיות P2/P3/P4 | טופס משותף (§0, מסך 3) |
| 5 | תובנות Follow-up | מסך 6 |
| 6 | סימולטור תקציב | מסך 5 |
| 7 | המלצות עסקיות ויציאה מהמערכת | רכיב `summary-recommendation` בכל מסך תוצאה + `sign-out-control` |

הביטוי החזותי של כל שלב, מול קריטריוני קבלה 23–27:

- **נקודת פתיחה ברורה לאדם זר (23):** Login → `authenticated-shell`; סדר
  `app-nav` תואם את סדר המסע (§1.4).
- **חמש דרישות המקור נגישות מ-Overview (24):** דרך `capability-index`
  (§1.4, §3.4).
- **P4S מזוהה כציון לרוכש ידוע אחרי מעקב 1 וחלון חודשי סגור (25):** כותרת
  ויחידה שונות מ-P4, ⛔ לא הבחנה צבעונית (§2.4).
- **Follow-up, תקציב והמלצות נגישים בניווט ברור (26):** דרך `app-nav`,
  בתוך `authenticated-shell`.
- **ההסבר והפעולה המומלצת גלויים לצד התוצאה או הגרף (27):** קבוצות
  הפריסה ב-§3.4 מצמידות כל `prediction-panel`/`chart-live` ל-
  `summary-recommendation` שלו; תוכן ההסבר עצמו — §6.

⛔ **אין צילום Stitch המוצג כהוכחה למסע** (קריטריון 28) · ⛔ **אין פרטי
דמו** בשום תוצר עיצוב — מסך Login מציג שדות ריקים בלבד (קריטריון 29,
`PHASE10.md` §יג).

---

## 9. מטריצת כיסוי Stitch (checkpoint 9, קריטריון 30)

⚠ **הכרעת סקופ מפורשת של המשתמש, לא "הקבצים קיימים" בשקט, ולא "הפניה
לטקסט = נכס חזותי":** מצבים שקיימים רק **כתוצאה** מבקשה/תגובה חיה —
`loading`, `error`, `empty`, `401`, `403`, `OOD`, כשל חלקי של פאנל —
וכן מצב ה-`prefill` של P4S, **ניתן היה** לעצב כמסכים סטטיים נוספים
ב-Stitch (כמו ששת המסכים הקיימים); זו אינה מגבלה טכנית של הכלי. המשתמש
בחר במפורש **שלא** ליצור וריאנטים נוספים ולהסתפק בששת המסכים הקיימים,
כדי לצמצם את היקף העבודה. ההכרעה: **הם אינם מכוסים חזותית בפאזה 10
ונדחים לפאזה 11** (שם האפליקציה עולה בפועל וניתן לצלם מצב חי אמיתי
במקום עוד מוקאפ) — ⛔ אין וריאנט Stitch בשבילם ואין נכס תמונה, וההפניה
לטבלאות §2/`IA.md` שלהלן היא **מקור להתנהגות המוגדרת**, לא תחליף לנכס
חזותי. קריטריון 30 עודכן בהתאם (`PHASE10.md` §ט) כדי לשקף את הדחייה
במפורש, לא כ"מכוסה".

### 9.1 — ששת מסכי ה-Desktop, מסלול תקין

| מסך | נכס |
|---|---|
| Login | `docs/design/login.jpg` |
| Overview | `docs/design/overview.jpg` |
| טופס תחזיות משותף | `docs/design/shared-form.jpg` |
| ציון לקוח-על (P4S) | `docs/design/p4s.jpg` |
| סימולטור תקציב | `docs/design/budget-simulator.jpg` |
| Follow-up | `docs/design/followup.jpg` |

### 9.2 — מצב חזותי מובחן (`loading`/`error`/`empty`/`401`/`403`/`OOD`/כשל חלקי) — ⛔ אינם מכוסים חזותית בפאזה 10, נדחים לפאזה 11

| מצב | מקור התנהגות (לא נכס חזותי) | הערה |
|---|---|---|
| `loading` | §2.1 | תלוי בקשה חיה בזמן טעינה; אין וריאנט Stitch |
| `error` | §2.1 | תלוי תגובת שגיאה חיה; כשל חלקי פר-פאנל מתועד באותה טבלה |
| `empty` | §2.1 | תוכן ממשי קיים **רק** ב**טופס התחזיות המשותף** וב-**P4S** (מצב "ללא דוגמה"); ⛔ **לא רלוונטי** ב-`Login`, ואינו מצב לגיטימי כלל ב-Overview/Follow-up/Budget Simulator (ר' §2.1 לניסוח המדויק של כל מסך) |
| `401` | §2.6 | תלוי session שפג; אין וריאנט Stitch |
| `403` | §2.6 | תלוי הרשאה חסומה; אין וריאנט Stitch |
| `OOD` (טופס משותף) | §2.2 | תלוי ערך קלט מחוץ לתחום האימון בתגובה חיה |
| `OOD` (P4S) | §2.3 | כנ"ל |

### 9.3 — מסלול P4S: הזנה ידנית מול `prefill`

| מצב | כיסוי |
|---|---|
| תרחיש עצמאי (הזנה ידנית) | ✅ **מכוסה חזותית** — `docs/design/p4s.jpg` הוא בדיוק המצב הזה |
| דוגמה טעונה (`prefill`) | ⛔ **אינו מכוסה חזותית בפאזה 10** — דורש בחירה מבורר חי; אין וריאנט Stitch. נדחה לפאזה 11. התנהגותו מוגדרת ב-`IA.md` §3א.3.1, שורת "דוגמה טעונה" |

### 9.4 — D9 לצד כל תוצאה וכל גרף

| מסך | נכס |
|---|---|
| טופס תחזיות משותף (שלושה פאנלים) | `docs/design/shared-form.jpg` |
| ציון לקוח-על (P4S) | `docs/design/p4s.jpg` |
| Overview (גרף המרה) | `docs/design/overview.jpg` |
| סימולטור תקציב (גרף דירוג) | `docs/design/budget-simulator.jpg` |
| Follow-up (שני גרפים) | `docs/design/followup.jpg` |

## 10. מה עדיין לא כתוב כאן

⛔ רשימה מפורשת, כדי שלא יונח בטעות שהיא קיימת:

⚠ checkpoints 1–9 הושלמו (`app/static/tokens.css`, `tests/test_design_tokens.py`,
§3.4, §4.1, §6, §7, §8, §9) — שורותיהן הוסרו מכאן. **אין כרגע פריט פתוח
בהיקף `DESIGN.md` עצמו** — checkpoints 10–12 (בדיקה חזותית ידנית, החלפת
המוקאפ ההיסטורי ב-`ROADMAP.html`, ביקורת קוד/push/PR/מיזוג) אינם דורשים
תוכן נוסף במסמך הזה.
