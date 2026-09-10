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
> ערכי ה-tokens (checkpoint 3), פריסות desktop/mobile ומפרט Dataviz
> (checkpoint 5), מטריצת D9 בת שש העמודות ומסע המשתמש (checkpoint 6),
> וצילומי מסכים/מטריצת כיסוי (checkpoint 9) — ⛔ **טרם נכתבו**; אין
> להניח שהם קיימים כאן.

---

## 0. ששת המסכים — מפה

| # | מסך | תוכן עיקרי | מקור מפרט |
|---|---|---|---|
| 1 | Login | קיים מפאזה 4 — מבנה/תוכן ללא שינוי; המראה מיושם בפאזה 11 | `IA.md` §1, `PHASE10.md` D4 |
| 2 | Overview | אינדקס חמש שאלות המייסדת + טבלת טיירים + גרף המרה | `IA.md` §2, `PHASE10.md` D8, מסך 2 |
| 3 | טופס חיזוי משותף (P2·P3·P4) | 13 שדות, prefill חובה, שלושה פאנלי תוצאה | `IA.md` §3, `PHASE10.md` מסך 3 |
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
| `prediction-primary` | התוצאה הראשית של פאנל חיזוי — מספר/אחוז בולט (`תחזית: 24 חודשים`, `נטייה לאפסייל: 62%`, `ציון לקוח-על: 71`) | טיפוגרפיה ראשית; ⛔ **אינו** `--color-positive`/`--color-negative` בשום פאנל תחזית (D10) |
| `prediction-range` | טווח משני גלוי ל-P2 (`18–31 חודשים`, בלי אחוז) | `--color-uncertain`, whisker |
| `propensity-band-badge` | תווית קטגוריה `below_base`/`near_base`/`above_base` (מקור: `IA.md` §4) — P3, P4, P4S | טקסט + אייקון (⛔ לא צבע בלבד), `--color-uncertain` נייטרלי |
| `base-rate-line` | ⚠ **נוסף ב-checkpoint 2**, כתוצר ישיר של מיפוי `base_rate` מול `app/schemas.py` — לא היה לו רכיב בכלל בגרסת checkpoint 1. שורת השוואה משנית: `event_probability` מול `base_rate` + הפרש בנקודות. P3/P4/P4S | — |
| `evidence-badge` | תג רמת ראיות — שתי רמות (P2/P3/P4/P4S: `low`/ריק) או שלוש (P6: `high`/`medium`/`low`). ⚠ **כשהרמה `low`, הרכיב נושא גם את הודעת `UnobservedBudgetWarning`** (הערך שלא נצפה) — לא רק תג ריק (§6) | `evidence-high` · `evidence-medium` · `evidence-low` |
| `calibration-badge` | תג `calibrated`/`uncalibrated` — **גם ב-P4S**, אך שם **נעול ל-`calibrated` בלבד**; `uncalibrated` אפשרי רק ב-P3/P4 (ר' §2.4) | `calibrated` · `uncalibrated` |
| `model-disclaimer` | הסתייגות גלויה בשפה פשוטה (P2 מנוף, P4 הבהרת proxy, P4S אומדן-לא-הבטחה) | `model-disclaimer`, טיפוגרפיה משנית שאינה מוסתרת |
| `model-details` | `<details>` מתקפל — `model_version`, `model_algorithm`, `metrics`, שיטת אינטרוול/כיול | — |
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
| `field-input` | רכיב בסיס בשני וריאנטים: **וריאנט חיזוי** — `<input type="number" step="1" min="0" required>`, שדה מספר שלם/סופי/אי-שלילי (13 שדות הטופס המשותף, 4 שדות P4S) · **וריאנט Login** — `<input type="email" required>`/`<input type="password" required>`, ⛔ בלי הגבלות המספר השלם של וריאנט החיזוי | — |
| `field-label` | רכיב בסיס בשני וריאנטים: **וריאנט חיזוי** — תווית עסקית בעברית + שם טכני משני + יחידה (D11, §2.5) · **וריאנט Login** — תווית רגילה בעברית (`אימייל`, `סיסמה`) בלבד, ⛔ בלי שם טכני ובלי יחידה — D11 חל רק על שדות חיזוי | — |
| `prefill-picker` | בורר טעינת דוגמה היסטורית — **שני מופעים נפרדים**: אחד לטופס המשותף (§3.3), אחד ל-P4S (§3א.3) | — |
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
| `founder-question-index` | אינדקס חמש שאלות המייסדת ב-Overview — חמישה כרטיסים לארבעה יעדים (D8) | — |
| `tier-table` | טבלת טיירי תקציב ב-Overview; שורת `gap` מסומנת בנפרד | `color-tier-1` · `color-tier-2` · `color-tier-3` |
| `overlap-alert` | הודעת חפיפת שתי האסטרטגיות המובילות ב-Simulator — **הרכיב הבולט ביותר במסך** | `--color-uncertain` |
| `strategy-row` | שורת אסטרטגיה בסימולטור — רווח + טווח + `n` + רמת ראיות | `evidence-high` · `evidence-medium` · `evidence-low` |
| `summary-recommendation` | רכיב D9 בן ארבע שכבות — תשובה / מה זה אומר / מה כדאי לעשות / חשוב לדעת. חוזר על כל מסך תוצאה/תובנה (⛔ לא Login) | `model-disclaimer` לשכבת "חשוב לדעת" |
| `chart-live` | גרף SVG חי — ארבע מופעים (§4). **ה-fallback הטבלאי הנגיש הוא חלק מהרכיב עצמו, ⛔ לא רכיב נפרד** — `chart-live` תמיד מרנדר את שניהם יחד | ≤5 צבעים סמנטיים |

---

## 2. מלאי מצבים

⚠ **כל מצב ב-`IA.md` §9 מופיע כאן** (דרישת קבלה של checkpoint 1).

### 2.1 — מצבים לכל מסך (מקור: `IA.md` §9.1)

| מסך | `loading` | `empty` | `error` | `OOD` |
|---|---|---|---|---|
| **Login** (`login-form`) | בדיקת session + טעינת `/api/config` — `panel-loading` | ⛔ לא רלוונטי | כשל `/api/config` → `panel-error` ברמת מסך; כשל התחברות → הודעה בטופס | ⛔ לא רלוונטי |
| **Overview** | טעינת `budget-tiers` — `panel-loading` | ⛔ **אין `empty` לגיטימי** — `200` עם אפס שורות הוא שגיאת זמינות, מוצג כ-`panel-error` | `panel-error` + ניסיון חוזר; ⛔ אין הצגת נתונים חלקיים | ⛔ לא רלוונטי |
| **טופס חיזוי משותף** (שלושה `prediction-panel`) | prefill נטען + שלוש בקשות חיזוי (דור אחד משותף) — `panel-loading` | טרם נשלח: כל `prediction-primary` מסביר מה יוצג בו; prefill בלי שורות → הודעה + מילוי ידני | **פר-פאנל** — `panel-error` בתוך ה-`prediction-panel` שנפל; שני ה-`prediction-panel` האחרים ממשיכים | ✅ **פר-פאנל** — `ood-banner` (§2.2) |
| **ציון לקוח-על (P4S)** (`prediction-panel` וריאנט P4S) | prefill נפרד נטען + בקשה אחת (דור עצמאי) — `panel-loading` | טרם נשלח: `prediction-primary` מסביר מה יוצג; prefill בלי שורות → הודעה + מילוי ידני | פאנל יחיד — `panel-error` בתוך ה-`prediction-panel` + ניסיון חוזר | ✅ **על ארבעת שדותיו בלבד** — `ood-banner` (§2.3) |
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
("נטייה להפניה" מול "ציון לקוח-על מוקדם"), יחידה שונה (`71%` מול `71`),
מסך נפרד. ⛔ ל-P4S אין `prediction-range` — אין `lower_bound`/`upper_bound`
בסכמה שלו.

### 2.5 — ולידציה חוסמת (מקור: `IA.md` §3.2/§3א.2)

| מסך | כללים | תגובה |
|---|---|---|
| טופס משותף (13 שדות) | 5 כללים: `num_leads>0` · `leads_answered≤num_leads` · שרשרת יורדת `leads_answered≥followup_1≥…≥followup_5` · `closed+not_closed=followup_5` · אי-שליליות בכל 13 | `submit-blocked-message`, חוסם שליחה — ⚠ **אינה** בדיקת OOD |
| P4S (4 שדות) | 4 כללים: `num_leads>0` · `leads_answered≤num_leads` · `followup_1≤leads_answered` · אי-שליליות (מקור: `IA.md` §3א.2 — כלל האי-שליליות מהשורה שמעל חל גם כאן; כלל ה-`closed+not_closed=followup_5` והמשך שרשרת הירידה מ-`followup_2` ואילך אינם ישימים, השדות שהם נוגעים בהם אינם במסך זה) | `submit-blocked-message`, חוסם שליחה |

### 2.6 — 401 מול 403 (מקור: `IA.md` §9.3)

| קוד | רכיב | תוכן |
|---|---|---|
| 401 | `auth-redirect` | אין session/פג תוקף → מסך Login + הודעה; תוכן הטופס **אינו** נשמר |
| 403 | `forbidden-notice` | מאומת בלי `organization=northbound` → הודעת חוסר הרשאה, ⛔ בלי נתונים, בלי ניסיון חוזר, בלי חזרה ל-Login; `sign-out-control` נשאר זמין בתוך `authenticated-shell` |

### 2.7 — תשובות מאוחרות ומוני דור (מקור: `IA.md` §9.4/§9.4א)

| מסך | מונה דור | עולה ב |
|---|---|---|
| טופס משותף (P2+P3+P4) | **אחד משותף** לשלוש הבקשות | שינוי כל אחד מ-13 השדות · בחירת שורת prefill אחרת (בבורר של הטופס) · יציאה מהחשבון |
| ציון לקוח-על (P4S) | **עצמאי, נפרד לחלוטין** | שינוי אחד מארבעת שדות P4S · בחירת שורת prefill אחרת (בבורר הנפרד שלו) · יציאה מהחשבון |

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
| `color-tier-1` · `color-tier-2` · `color-tier-3` (כל אחד זוג `-fg`/`-bg`) | טיירי תקציב Low/Mid/High — **סדרה מסודרת** (רמפה עוקבת, לא שלושה גוונים בלתי-קשורים), כרקע `tier-table` בלבד | — |

⛔ **כלל D10, חוצה-מסכים:** `prediction-primary` בכל ארבע משימות החיזוי
(P2/P3/P4/P4S) צורך **תמיד** `--color-uncertain` או ניטרלי, **לעולם לא**
`--color-positive`/`--color-negative` — גם כשהתחזית "טובה". `ציון לקוח-על:
71` בירוק משדר "זה כבר קרה", וזו בדיוק ההטעיה שהכלל אוסר.

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

---

## 4. Dataviz — מלאי תצוגות

⚠ מפרט פריסה מלא (desktop/mobile, מידות, breakpoints) נכתב ב-checkpoint 5.
כאן — מלאי התצוגות וכלליהן המחייבים (מקור: `PHASE10.md` §ו, `IA.md` §7).

**ארבע תצוגות חיות**, כולן `chart-live` — SVG ידני ונגיש, ⛔ בלי ספריית
תרשימים:

| # | תצוגה | מסך |
|---|---|---|
| 1 | שיעור המרה לפי טייר תקציב | Overview |
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

## 6. מה עדיין לא כתוב כאן

⛔ רשימה מפורשת, כדי שלא יונח בטעות שהיא קיימת:

| תוכן | checkpoint |
|---|---|
| ערכי tokens בפועל (hex/px/rem) | 3 |
| בדיקות אוטומטיות (`tests/test_design_tokens.py`) | 4 |
| מפרט פריסה desktop/mobile מלא (breakpoints, מידות) | 5 |
| מטריצת D9 בת שש העמודות (שאלה·תשובה·משמעות·פעולה·מגבלה·מקור ראיה) לכל פאנל/גרף, ומסע המשתמש בן שבעת השלבים. ⚠ **בתא הראשון (שאלה) בלבד, כל שורה חייבת לשאת מזהה חד-משמעי לאחד משמונת היעדים הנעולים** (`PHASE10.md` D9: Overview · P2 · P3 · P4 · P4S · Budget Simulator · שני גרפי Follow-up — נשירה ו-`calls_to_closed`), ⛔ בדיוק פעם אחת לכל יעד — כך שבדיקה 9 (`test_design_tokens.py`) תוכל לזהות כל שורה. חמשת התאים האחרים רשאים להזכיר יעדים אחרים בחופשיות (למשל תשובת Overview שמפנה ל-P2, או הבחנת P4/P4S זו מזו) — הזיהוי בודק את תא השאלה בלבד, לא את השורה כולה | 6 |
| מפת שדות P4S (D11) — תווית עסקית, שם טכני, יחידה, מועד מדידה, הסבר | 6 (משולב עם מטריצת D9) |
| reference חזותי מ-Stitch | 7–8 (אישור נפרד) |
| צילומי מסכים + מטריצת כיסוי מלאה | 9 |
