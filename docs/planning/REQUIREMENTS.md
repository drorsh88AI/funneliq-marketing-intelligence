# מרשם דרישות הבריף — 73 דרישות אטומיות (B1–B65)

> **מקור אמת יחיד לדרישות `FunnelIQ_Assignment.html`.** כל שורה היא חובה אטומית אחת
> שחולצה מהבריף, עם ציטוט מילולי מלא, בעלים יחיד, תורמים, מאמת, סטטוס וראיה.
>
> נבנה ואומת כחלק מ"תוכנית היישור לבריף" ב-08–09.09.2026 (ר' `docs/planning/codex-review.md`
> ותכנון פאזה 8A). `tests/test_requirements_traceability.py` אוכף את שלמותו: כל `source_quote`
> חייב להימצא מילולית בטקסט הגלוי של הבריף, לכל דרישה יש בעלים יחיד, ולכל דרישה `done`
> יש ראיה. מזהה `B47` הוסר במפורש (סעיף אחרון) ואינו יתום — הוא לא נמחק בשתיקה.
>
> **מקרא סטטוס:** `done` בוצע ומאומת · `planned` בעלים ידוע, טרם בוצע · `gap` נתון קיים
> אך הכתיבה חסרה · `N/A` אופציונלי בבריף ונדחה ביודעין · `parent` דרישת-על שאינה נסגרת
> עצמאית — ר' הילדים בעמודת הראיה.

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
| **B8** | §04 | "Your application must read from Supabase at runtime (for at least one feature, e.g. serving historical records or computing insights), using credentials from environment variables." | קריאה מ-Supabase בזמן ריצה עם credentials מ-env | 9 | 3 | 12 | planned | `/api/insights/followup`, `/api/insights/budget-tiers` ממומשים ונבדקו מקומית (`docs/planning/PHASE9.md` checkpoints 8–9); ⛔ ראיה חיה (ק' 72–73) טרם בוצעה — ר' PHASE9.md §8 |
| **B12** | §04 | "Tie it together with access control: enable Row Level Security and write policies so the database itself enforces that only authenticated users can read the data. For RLS to actually matter, user-facing reads should reach Supabase with the signed-in user's access token (or your API verifies the user's JWT before serving) — a backend that reads everything with the service key bypasses your policies." | RLS + policies, וקריאות המשתמש נושאות את הטוקן שלו | 9 | 3 | 12 | planned | policy `funnel_records_northbound_select`; views `security_invoker=true`; `app/supabase_client.py` — לקוח פר-בקשה עם JWT המשתמש, נבדק מול Mock שהטוקן מגיע בפועל (D4, `docs/planning/PHASE9.md` checkpoint 7); ⛔ ראיה חיה מול RLS אמיתי (ק' 72–73) טרם בוצעה |

## §04 Supabase — אימות

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B9** | §04 | "Build a login screen using Supabase Auth (email + password at minimum)." | מסך התחברות email+password | 4 | — | 12 | done | `app/static/index.html` + `app.js`; 11 בדיקות ב-`test_auth.py` |
| **B10** | §04 | "Handle the session properly: an unauthenticated visitor sees only the login screen; a signed-in user reaches the dashboard and predictions; sign-out works and clears the session." | ניהול session מלא כולל גישה לדשבורד ולחיזויים | 11 | 4 | 12 | planned | לוגין/יציאה קיימים מפאזה 4 |
| **B11** | §04 | "Use the public anon key in the browser for the login flow — never expose the service key client-side. Keep any privileged operations server-side." | anon בדפדפן, service לעולם לא בצד לקוח | 4 | 9 | 12 | done | `test_config.py` — `"sb_secret" not in response.text`; `render.yaml` ללא `SUPABASE_SECRET_KEY` |

## §04 פריסה

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B13** | §04 | "Deploy your service to Railway so it's reachable at a public URL." | השירות זמין ב-URL ציבורי | 2 | — | 12 | done | ר' B64; `render.yaml` |
| **B14** | §04 | "Secrets (Supabase keys, config) are set as Railway environment variables, never hard-coded." | secrets כמשתני סביבה | 2 | — | 12 | done | `render.yaml` `sync:false` לשני שדות בלבד |
| **B15** | §04 | "Connect the Railway service to your GitHub repo so pushes trigger a redeploy." | push מפעיל redeploy | 2 | — | 12 | done | `autoDeployTrigger: commit`, `branch: main` |
| **B16** | §04 | "Expose a health-check endpoint and confirm the deployment survives a restart." | health-check + שרידות restart | 2 | — | 12 | done | `/health` ב-`app/main.py`; `healthCheckPath: /health` |

## §05 חבילה 1

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B17** | §05.1 | "a short written findings note (in the README or a /docs file)" | מסמך ממצאים כתוב | 5 | 13 | 12 | done | `docs/FINDINGS.md` |
| **B18** | §05.1 | "covering missing-value handling" | טיפול בערכים חסרים מתועד | 5 | — | 12 | done | `findings.json.missing_values` — 3,500 שורות, 4+29+33 |
| **B19** | §05.1 | "a correlation analysis against cumulative_profit" | קורלציה מול `cumulative_profit` | 5 | — | 12 | done | `findings.json.correlations` — 17 עמודות |
| **B20** | §05.1 | "the shape of the ad_budget → num_leads relationship" | צורת הקשר תקציב→לידים | 5 | — | 12 | done | `findings.json.ad_budget_leads_curve` (16 רמות); `ad_budget_leads_curve.svg` |
| **B21** | §05.1 | "and conversion rate (closed / num_leads) across budget tiers — Low (≤1500), Mid (2000–5000), High (>5000)." | שיעור המרה לפי שלושת הטיירים | 5 | 9, 11 | 12 | done | `docs/findings.json.budget_tiers` — Low **0.04524** (4.5%, n=780) · Mid **0.08220** (8.2%, n=1,717) · High **0.05433** (5.4%, n=1,003) · gap n=0 |
| **B22** | §05.1 | "How many rows are incomplete, and how did you handle them?" | תשובה כתובה | 5 | 13 | 12 | done | `FINDINGS.md` §חסרים |
| **B23** | §05.1 | "Does more budget buy proportionally more leads, or do you see diminishing returns?" | תשובה כתובה | 5 | 13 | 12 | done | `FINDINGS.md`; `ad_budget_leads_curve.svg` |
| **B24** | §05.1 | "Which budget tier converts best — and does that surprise you?" | תשובה כתובה | 5 | 13 | 12 | done | `FINDINGS.md` — Mid 8.2%, לא הגבוה |

## §05 חבילה 2

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B25** | §05.2 | "three trained models — XGBoost, LightGBM, and CatBoost" | שלושת המודלים אומנו | 6 | — | 12 | done | `metrics.json.P2_selection.eligible = [catboost, lightgbm, xgboost]` |
| **B26** | §05.2 | "compared with 5-fold cross-validation on RMSE and R²" | השוואה ב-5-fold CV על RMSE ו-R² | 6 | — | 12 | done | `metrics.json.P2` — `mean_rmse`, `mean_r2` לכל אלגוריתם |
| **B27** | §05.2 | "Extract and compare feature importances across all three." | חילוץ importance לשלושת המודלים | 6 | 13 | 12 | done | `docs/feature_importance_P2.svg` + `metrics.json.global_feature_importance.P2` — אומת: `catboost`, `lightgbm`, `xgboost` |
| **B28** | §05.2 | "Expose the prediction through your app." | חשיפת חיזוי ה-LTV באפליקציה | 9 | 11 | 12 | planned | `/api/predict/ltv` ממומש ונבדק מול הארטיפקט (`docs/planning/PHASE9.md` checkpoint 5) — חיזוי תואם בדיוק לערך שנמדד בתכנון; ⛔ ראיה חיה מול Render (ק' 75) טרם בוצעה |
| **B29a** | §05.2 | "Should cumulative_profit be a feature here? Justify it." | הצדקה כתובה להחרגת `cumulative_profit` מ-P2 | 5 | 6, 13 | 12 | done | `docs/planning/PHASE5.md` D2 · `docs/feature_matrix.md:66` — `Excluded` ב-P2/P3/P4, *"תוצאה מאוחרת/מצטברת… ברשימת הדליפה המפורשת בכולן"* · commit `339736b` — *"feat(phase5): checkpoint 6 — app/features.py, feature_matrix.md, test_features.py"* |
| **B29b** | §05.2 | "Which features dominate, and do the three models agree?" | השוואה כתובה בין שלושת המודלים | 13 | 6 | 12 | gap | הנתון ב-B27; הכתיבה חסרה |
| **B29c** | §05.2 | "In two sentences, what's the strongest lever on customer longevity, and what should Northbound do about it?" | שני משפטים: מנוף + המלצה | 13 | 6 | 12 | gap | — |

## §05 חבילה 3

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B30** | §05.3 | "three classifiers with 5-fold stratified CV" | שלושה מסווגים ב-CV מרובד | 6 | — | 12 | done | `metrics.json.P3_selection.eligible = [catboost, lightgbm, xgboost]`; `metrics.json.P3` עם `fold_scores` בני 5 |
| **B31** | §05.3 | "Check the class balance first and decide whether class-imbalance handling (e.g. scale_pos_weight or class weights) is warranted — justify either way." | בדיקת איזון + החלטה מנומקת | 6 | 13 | 12 | done | `metrics.json.P3_weighted_comparison` |
| **B32** | §05.3 | "Report Accuracy, Precision, Recall, F1 and ROC-AUC, alongside the majority-class baseline." | דיווח חמשת המדדים | 13 | 6 | 12 | gap | `P3_holdout` — acc 0.7615, f1 0.7722, prec 0.6919, rec 0.8737, auc 0.7894 |
| **B33** | §05.3 | "alongside the majority-class baseline" | דיווח מול baseline הרוב | 6 | 11, 13 | 12 | done | `metrics.json.P3.dummy.mean_accuracy = 0.53656` |
| **B34** | §05.3 | "Plot importances for your best model." | גרף importance למנצח | 6 | 13 | 12 | done | `docs/feature_importance_P3.svg` |
| **B35** | §05.3 | "Design a simple business rule (e.g. "if LTV > X and CAC < Y, flag for outreach") and compare it against your model's predictions" | כלל עסקי + השוואה למודל | 6 | 13 | 12 | done | `metrics.json.P3_manual_rules` — `ltv_months>23.0`, `cac<1000.0` |
| **B36** | §02 | "Each answer must be reachable through your deployed, signed-in application — not just printed once in a notebook cell." | חיזוי ה-upsell נגיש דרך האפליקציה | 9 | 11 | 12 | planned | `/api/predict/upsell` ממומש ונבדק (`docs/planning/PHASE9.md` checkpoint 5); ⚠ חבילה 3 אינה נושאת שורת expose, המקור §02; ⛔ ראיה חיה (ק' 75) טרם בוצעה — "deployed" הוא התנאי המילולי שטרם התקיים |
| **B37a** | §05.3 | "Is accuracy a sufficient metric here?" | תשובה כתובה | 13 | 6 | 12 | gap | — |
| **B37b** | §05.3 | "What does the majority-class baseline score, and how much does your model add?" | תשובה כתובה | 13 | 6 | 12 | gap | — |
| **B37c** | §05.3 | "Is upsell driven by one feature or a combination?" | תשובה כתובה | 13 | 6 | 12 | gap | — |
| **B37d** | §05.3 | "where does the rule win or lose?" | תשובה כתובה | 13 | 6 | 12 | gap | — |

## §05 חבילה 4

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B38** | §05.4 | "Build: a CatBoost classifier" | מסווג CatBoost נבנה | 6 | 13 | 12 | done | `PHASE6.md:693–695` — *"P4 — הזוכה Logistic (זכאי, מנצח CatBoost בפשטות)"*; `metrics.json.P4_selection`; One-SE + RSS ב-`train.py:1196`, לפני ה-Holdout |
| **B39** | §05.4 | "engineer a categorical budget-tier feature (Low/Mid/High) and let CatBoost handle it natively" | `budget_tier` בטיפול נייטיב | 6 | — | 12 | done | `train.py:243` `build_preprocessing_steps(encode_budget_tier=False)` |
| **B40** | §05.4 | "with hyperparameter tuning (search over learning rate, depth, and iterations)" | כוונון שלושת הצירים | 6 | — | 12 | done | `train.py:526` `catboost_param_distributions()` |
| **B41** | §05.4 | "Then build a scoring pipeline: given a new customer's early funnel data, output a 0–100 likelihood of becoming a super customer, served by your app." | ציון 0–100 ללקוח-על, מוגש באפליקציה | 8A | 9, 11 | 12 | planned | סתירה בבריף מול `Target: referred`; הרחבה שמרנית |
| **B42** | §05.4 | "Profile the super customers (referred = Yes, upsell = 1, long tenure): what share of total profit do they represent, and what's their average acquisition cost?" | פרופיל: אחוז רווח + CAC | 6 | 13 | 12 | done | `metrics.json.super_customer_profile` — n=529, 33.61% מהרווח, CAC 990.7 מול 1,437.5 (חיסכון 31.1%) |
| **B43** | §05.4 | "How could Northbound spot them earlier?" | תשובה כתובה | 13 | 8A | 12 | gap | `P4_early_funnel` + P4S |

## §05 חבילה 5

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B44** | §05.5 | "the dropout rate at each follow-up stage (followup_1→followup_5), visualized" | נשירה בכל שלב, ויזואלית | 5 | 9, 11 | 12 | done | `findings.json.funnel_dropoff` — 21.7/25.7/18.6/10.4/29.2%; `funnel_dropoff.svg` |
| **B45** | §05.5 | "plus a data-driven recommendation surfaced in the dashboard" | המלצה מוצגת בדשבורד | 11 | 5, 9 | 12 | planned | טקסט מ-SPEC §מסקנת P5 |
| **B46a** | §05.5 | "At which stage does dropout behave unexpectedly?" | תשובה כתובה | 5 | 13 | 12 | done | `funnel_dropoff.followup_4 = 0.10372` — הנמוך ביותר |
| **B46b** | §05.5 | "For deals that eventually closed, how many follow-ups did they typically take?" | תשובה כתובה | 5 | 13 | 12 | done | `findings.json.calls_to_closed.mean_calls_to_closed_closed_ge_2 = 3.348`; `closed_eq_1 = 5.650` ⚠ `calls_to_closed` הוא **ממוצע ברמת רשומה**, ⛔ לא היסטוריית שיחות פר-עסקה (PHASE0) |
| **B46c** | §05.5 | "Should Northbound change its follow-up policy — yes or no, and why?" | תשובה כתובה | 5 | 13 | 12 | done | `FINDINGS.md` §מסקנת P5 |

## §05 חבילה 6

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B48** | §05.6 | "a model that predicts cumulative_profit" | מודל שמנבא רווח מצטבר | 6 | — | 12 | done | `models/P6.joblib` (linear); `metrics.json.P6_holdout` — mae 3,678.9, rmse 4,590.9, r2 0.7961 |
| **B49** | §05.6 | "used to simulate allocation strategies built from campaign sizes the data actually covers (₪500–₪20,000)" | סימולציה בטווח שהנתונים מכסים | 6 | — | 12 | done | `models/P6_simulation.json` — ארבע אסטרטגיות |
| **B50** | §05.6 | "and a recommendation for which maximizes expected total profit" | המלצה איזו ממקסמת רווח | 11 | 6, 9, 13 | 12 | planned | ניסוח §8 בחלק א |
| **B51** | §05.6 | "Your simulator only knows each campaign's budget, so decide how to fill in the other features (a typical funnel profile per budget level is one reasonable approach)." | החלטה מתועדת על מילוי הפיצ'רים | 6 | — | 12 | done | פרופיל חציוני לפי טייר; `feature_matrix.md` `Derived` ב-P6 |
| **B52** | §05.6 | "Expose the simulator in your app." | חשיפת הסימולטור | 9 | 11 | 12 | planned | `/api/simulate/budget` ממומש כלוקאפ טהור על `P6_simulation.json` (`docs/planning/PHASE9.md` checkpoint 8, D11) — `P6.joblib` אינו נטען בשום מסלול; ⛔ ראיה חיה (ק' 75) טרם בוצעה |
| **B53a** | §05.6 | "Based on what your model learned about diminishing returns, does concentrating or spreading spend win?" | תשובה כתובה | 13 | 6 | 12 | gap | ניתן לענות חד-משמעית |
| **B53b** | §05.6 | "What would you tell the founder to do next month?" | תשובה כתובה | 13 | 6 | 12 | gap | — |

## §06 מה תבנה

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B54** | §06 | "A public GitHub repository — code, README.md, schema.sql, a CI workflow, and a commit history that shows how you worked." | חבילת ה-repo | parent | — | — | parent | ⛔ אינו נסגר עצמאית → B1, B2, B5, B6 |
| **B55a** | §06 | "A live application URL on Railway — a real link you can share that actually answers the founder's questions." | URL ציבורי חי | 2 | — | 12 | done | פאזה 2 checkpoint 14; Render לפי B64 |
| **B55b** | §06 | "A live application URL on Railway — a real link you can share that actually answers the founder's questions." | האפליקציה הפרוסה **עונה בפועל** לשאלות המייסדת | 12 | 9, 11, 13 | 12 | planned | ⚠ ה-URL חי (B55a) אך התוכן העסקי טרם קיים |
| **B56** | §06 | "A login-gated dashboard — a real Supabase Auth sign-in screen, not an open page, so the app behaves like the internal tool it's meant to be." | דשבורד מאחורי לוגין | 11 | 4 | 12 | planned | — |
| **B57** | §06 | "A short write-up (nice to keep as REPORT.md) capturing your findings and the business recommendations from the work packages" | `REPORT.md` עם ממצאים והמלצות | 13 | 5, 6 | 12 | planned | אינו קיים (אומת) |
| **B58** | §06 | "A quick demo — an optional 3–5 minute screen-recording of the deployed app in action." | הקלטת דמו | — | — | — | N/A | אופציונלי בבריף; נדחה ביודעין ב-SPEC |
| **B59** | §06 | "A stranger can open your live URL, sign in, get a prediction for a new customer, see the follow-up and budget insights, and read your recommendations — without you touching anything. Your repo tells them how it was built and how to run it themselves." | רף הסיום מקצה לקצה | 12 | 9, 11, 13 | 12 | planned | מתח "לקוח חדש" מרוכך ב-8A |

## §07 עקרונות

| # | מקור | ציטוט מהבריף | חובה | בעלים | תורמים | מאמת | סטטוס | ראיה |
|---|---|---|---|---|---|---|---|---|
| **B60** | §07 | "Reproducibility. Anyone (including future-you) should be able to clone the repo, follow the README, and stand it up. Pin your dependencies." | שחזוריות + הצמדה | 13 | 1 | 12 | planned | `requirements.txt` מוצמד; README חסר |
| **B61** | §07 | "Secrets stay secret. Everything sensitive goes in environment variables and is excluded by .gitignore — never commit an API key or .env." | secrets ב-env ומוחרגים | 1 | 2, 4 | 12 | done | `.gitignore` · `.env.example` שמות בלבד · **`PHASE4.md:371`** — `.env` מוחרג ואינו tracked · **`PHASE4.md:372`** — סריקת `sb_secret_`/`eyJhbGciOi` על עץ העבודה, כל היסטוריית הגיט בכל הענפים, וגוף+תגובות PR #14; אפס ערכים אמיתיים |
| **B62** | §07 | "Anon key in the browser, service key on the server. The login screen uses Supabase's public anon key; the service-role key never leaves your backend." | הפרדת המפתחות | 4 | 9 | 12 | done | `app/static/app.js:46-50` — `config.supabase_publishable_key` → `createClient`; `app/auth.py:31` — `SUPABASE_PUBLISHABLE_KEY` בלבד; `tests/test_config.py`. ⚠ ה-publishable key מחליף את ה-anon key בנוסח החדש; ה-secret key אינו נדרש ב-runtime ונשאר ב-`scripts/*.py` |
| **B63** | §07 | "No leakage without justification. If you include a feature that looks like an outcome, write down why it's legitimately available at prediction time." | הצדקה כתובה לכל פיצ'ר תוצאה-לכאורה | 8A | 5, 6 | 12 | done | `docs/planning/PHASE8A.md` §ד (מפת אינטגרציה) + §א/§ג D1-D2: `referred`/`upsell`/`ltv_months`/`cumulative_profit` מוחרגים כרכיבי-יעד או תוצאה מאוחרת; ארבעת `EARLY_FUNNEL_FEATURES` מתועדים כזמינים לפני רכישה (אותות משפך מוקדמים בלבד, עד `followup_1`) |
| **B64** | §07 | "Render or Fly.io are drop-in substitutes for this pillar if you prefer." | היתר לחלופת פריסה | 2 | — | 12 | done | **ההיתר להכרעת Render** |
| **B65** | §07 | "Credit what you borrow. Note snippets from docs or tutorials in comments or the README." | קרדיט למקורות שאולים | 13 | 4 | 12 | planned | ⚠ SRI מוכיח שלמות קובץ, ⛔ לא קרדיט |

---

## B47 — הוסר

חבילה 5 בבריף (§05.5) אינה נושאת שורת "expose the X in your app" נפרדת כמו חבילות
2/3/4/6 — היא מסתפקת ב-B44 (ויזואליזציה) ו-B45 (המלצה בדשבורד). מזהה `B47` שוריין
בסבב תכנון קודם עבור שורת expose שלא קיימת בפועל, ותוקן. **פאזה 9 היא contributor**
ל-B44 ול-B45 (המימוש שמאפשר את שתיהן), ⛔ אין דרישת בריף עצמאית לשחזר.

## סיכום כמותי

**73 דרישות אטומיות** (B1–B65 עם פיצולים, בניכוי B47 שהוסר): `done` 43 · `planned` 18 · `gap` 10 · `N/A` 1 · `parent` 1.
