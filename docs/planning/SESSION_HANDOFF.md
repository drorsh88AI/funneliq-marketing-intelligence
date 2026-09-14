# חפיפת שיחה — FunnelIQ

עודכן: 14.09.2026. מסמך זה מרכז את מצב העבודה המחייב לפתיחת שיחת Codex או
Claude חדשה, בלי להעביר אליה את היסטוריית השיחה הארוכה.

## נקודת פתיחה פעילה

- שפה: עברית, עניינית וקצרה. אם המשתמש טועה — להסביר לפני ביצוע.
- תיקייה: `C:\Users\dror_\AI\AI Course\9.Finel Project\Project 1`.
- ענף בסיס: `main`.
- בסיס מתועד: `c1d514e` — סגירת פאזה 10 לאחר merge commit `ef2eb83`.
- פאזה 10A: סגורה (`approved_for_execution` / `done`).
- פאזה 10: סגורה (`approved_for_execution` / `done`), checkpoints 0–12 הושלמו.
- PR #26 מוזג ל־`main` ב־14.09.2026, merge commit `ef2eb83`.
- **פאזה 11: `planning_status: approved_for_execution` / `execution_status:
  not_started`.** תכנון מפורט נכתב ונבדק ב־`docs/planning/PHASE11.md`
  (`P11-D1`–`P11-D15`, 13 checkpoints ביצוע + שער, 30 מקרי הפרכה), עבר שמונה
  טיוטות ביקורת Codex–Claude, והמשתמש אישר אותו לביצוע 14.09.2026.
- `main == origin/main`. עץ העבודה נושא כעת את תוצרי שלב התכנון (G1–G5)
  ומסמך החפיפה — טרם מקומטים.

## המשימה הבאה — סגירת שלב התכנון (G1–G5), ואז CP0

תוצרי התכנון נכתבו. השלב הבא הוא **לא** פתיחת `feat/dashboard` ישירות —
לפי `PHASE11.md` §ד ("מצב העץ"), תוצרי G1–G5 וקבצי החפיפה נסגרים תחילה
בקומיט תכנון אחד על ענף תכנון ייעודי, שעובר PR ו-CI ומוזג ל־`main`
(תואם לתקדים פאזה 10, `checkpoint 0`). **רק אחרי המיזוג** נפתח `feat/dashboard`
מ־`main` עם עץ נקי — זהו `checkpoint 0` של פאזה 11 עצמה, וכולל גם בדיקת
עשן קצרה וללא credentials על הפריסה החיה (`GET /health`, `GET
/api/insights/budget-tiers` ללא טוקן, השוואת `SHA-256` של
`business_facts.json`).

⛔ אין `git checkout -b`, commit, push, PR או merge בלי אישור נפרד ומפורש
לכל שלב — לפי פרוטוקול האישור הכפול ומדיניות השער האחיד ב-`CLAUDE.md`.

## תוצרי שלב התכנון שנכתבו (G1–G5)

1. **G1** — `docs/planning/PHASE11.md` נוצר: התכנון המלא.
2. **G2** — `docs/planning/REQUIREMENTS.md` עודכן: נוספה `B66` (§07 בבריף,
   הסעיף "Use AI tools… explain every line" שחסר במרשם); תוקנה עמודת
   `contributors` ב-11 שורות (הוסר מ-`B33`, נוסף ל-`B24`/`B29c`/`B42`/`B43`/
   `B46a`/`B46b`/`B46c`/`B53a`/`B53b`/`B65`). ⛔ אפס שינוי ב-`owner`/`status`/
   `evidence` של שורות קיימות. `_EXPECTED_IDS`/`_EXPECTED_STATUS_COUNTS`
   ב-`tests/test_requirements_traceability.py` עודכנו באותו קומיט (נדרש
   מפורשות על ידי הבדיקה עצמה). 14/14 בדיקות עקיבות+ROADMAP עברו.
3. **G3** — `ROADMAP.html` עודכן: כרטיס פאזה 11 (`planning_status:
   approved_for_execution`), מקרא העקיבות (74/B1–B66, `planned` 16), ותקציר
   שער 10→11. `node --check` על ה-JS המוטמע עבר.
4. **G4** — `docs/planning/SPEC.md` §Architecture עודכן: `app/static/js/`,
   `requirements-e2e.txt` ו-`e2e/` כנתיבים נפרדים בעץ.
5. **G5** — `docs/IA.md` §9.3 הורחב משני ענפים (401/403) לשבעה: כשל
   `/api/config`, אין session, `200`, 401, 403, 503, 500.

## מצב הדרישות והראיות

- ספירת המרשם הפעילה: 41 `done`, ‏16 `planned`, ‏15 `gap`, אחת `N/A` ואחת
  `parent` — **74** בסך הכול (B1–B66).
- `B10`/`B45`/`B50`/`B56` (בבעלות פאזה 11) נשארות `planned` גם בסגירת
  פאזה 11 — הסגירה דורשת ראיית קבלה חיה בפאזה 12, לא רק מימוש ובדיקות
  מקומיות. עמודת ה-`evidence` שלהן כן מתעדכנת בשלב 6 של `CP13`.
- `B59` אינה נסגרת בפאזה 11 או 12 לבדן: דורשת גם ראיית מסע חי מפאזה 12 וגם
  רכיב שחזור ב־README מפאזה 13.
- ראיית הבדיקות התקפה: `tests/test_requirements_traceability.py` +
  `tests/test_roadmap_render.py` — 14/14, לאחר עדכוני G2/G3. אין להריץ
  אותן שוב ללא אי־ודאות חדשה.
- אין לפתוח שוב Holdout או להריץ מודלים. חריגת S9 מפאזה 6 נשארת בתוקף.

## מקורות חובה לפני ביצוע

1. `AGENTS.md` ו־`CLAUDE.md` — אם יש סתירה ביניהם, להעלות אותה כבאג סנכרון.
2. `docs/planning/PHASE11.md` — התכנון המלא, מקור האמת לביצוע פאזה 11.
3. `FunnelIQ_Assignment.html` · `docs/planning/REQUIREMENTS.md` ·
   `docs/planning/SPEC.md` · `docs/IA.md` · `docs/DESIGN.md`.
4. `docs/planning/PHASE10.md` ו־`docs/planning/PHASE10A.md` — תוצרי הפאזות
   הסגורות.
5. החוזים החיים: `app/schemas.py`, `app/auth.py`, `docs/api/openapi.json`,
   `app/features.py`, `app/static/business_facts.json`.

## החלטות נעולות

- Render ולא Railway; בלי notebook.
- `app/features.py` הוא מקור האמת היחיד לרשימות פיצ'רים.
- anon/publishable key בלבד בדפדפן; service/secret key רק בצד השרת המקומי.
- קריאות נתונים למשתמש נושאות את ה־JWT שלו כדי ש־RLS תיאכף בפועל.
- `README.md` באנגלית; `REPORT.md` בעברית.
- P4 הוא חיזוי referral ואינו ציון לקוח־על. P4S הוא ציון לקוח־על לרוכש ידוע
  אחרי מעקב 1 וסגירת חלון חודשי; ההסתברות מה־API מומרת למספר שלם 0–100
  בממשק (`Math.round(p*100)`, `P11-D12`).
- CatBoost הוא מודל P4S הפעיל מכוח דרישת הבריף, אף ש־Logistic ההיסטורי מעט
  חזק יותר; הציון הוא אות מסייע לבדיקה ידנית בלבד.
- `100x500` מדורגת ראשונה בסימולציה אך אינה המלצה. אם בוחנים חלופה, ההמלצה
  הזהירה היא פיילוט מוגבל של `25x2000`.
- צילומי Stitch הם ראיית עיצוב בלבד. `tokens.css`, ‏`DESIGN.md` ו־`IA.md` הם
  מקורות המימוש; אין לייבא markup מ־Stitch.
- **פאזה 11: SPA ב-vanilla JS ללא תלות frontend/framework/build step
  חדשה; Playwright כתלות-בדיקה בלבד, מבודדת מ-CI וב-`e2e/`** (`P11-D1`,
  `P11-D7`). כלל תיקון מקור: סתירה בין הבריף/SPEC/IA/DESIGN לחוזה החי עוצרת
  checkpoint ⛔ ואינה נעקפת בקוד ה-frontend.

## מדיניות בדיקות לתכנון/ביצוע

לפני הרצה יש לציין איזו אי־ודאות חדשה היא פותרת. שינויי תיעוד בלבד נבדקים
ב־diff; מותרת בדיקה ממוקדת של מבנה `ROADMAP.html` אם השינוי עלול לשבור HTML
או JavaScript. אין להריץ `pytest` מלא, מודלים, Holdout או סריקת סודות מחדש
רק כדי לאשר ראיה קיימת.
