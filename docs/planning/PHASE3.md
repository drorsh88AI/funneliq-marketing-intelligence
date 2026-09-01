# פאזה 3 — Supabase + RLS

> **סטטוס:** תכנון מפורט · טרם אושר לביצוע
> **Branch מתוכנן:** `feat/supabase-data`
> **גבול הפאזה:** שכבת נתונים והרשאות בלבד. אין Auth UI, אין יצירת משתמשים,
> אין endpoints עסקיים, אין EDA ואין מודלים.
>
> ⚠ מסמך זה הוא **כתיבה מחדש** של טיוטה קודמת. הטיוטה נכתבה לפני בדיקת המצב
> בפועל, וארבע מהנחותיה הופרכו במדידה (סעיף ב'). אין לפעול לפי הטיוטה.

---

## א. מטרת הפאזה

להקים ב-Supabase עותק שחזורי ומאובטח של 3,500 רשומות המקור, כך שהאפליקציה
תוכל לקרוא נתוני Runtime בשם משתמש מחובר ו-RLS תיאכף בפועל. הטעינה מתבצעת
בסקריפט חוזר, בלי להעלות את ה-CSV או secrets לגיט.

---

## ב. מצב מאומת — נבדק 01.09.2026, לא הונח

| ממצא | ראיה |
|---|---|
| פאזה 2 סגורה נקי | `main` == `origin/main`; PR #1–#10 מוזגו; CI `success` על `a928e4b` |
| פרויקט Supabase — **נוצר היום ידנית** | `funneliq` · ref `zbxqwcwiirnrfnkzpwri` · `eu-central-1` · `ACTIVE_HEALTHY` · PG 17.6.1.166 · נוצר `2026-09-01T12:36:08Z` · מסלול free, עלות `$0` |
| סכמת `public` ריקה | `list_tables` → `[]` |
| הגדרות מסך היצירה | אינטגרציית GitHub — **לא** · Data API — **כן** (`public`) · Automatically expose new tables — **לא** · Automatic RLS — **כן** |
| **אין Docker** | `docker: command not found` |
| כלים זמינים | `supabase` CLI 2.109.1, מחובר · MCP של Supabase פעיל · **אין `psql`** |
| `security_invoker` נתמך | תיעוד Supabase: PG 15+; הפרויקט על PG 17 |

### ארבע ההנחות שהופרכו מול הטיוטה

| # | הטיוטה הניחה | הנמדד בפועל |
|---|---|---|
| 1 | "פרויקט Supabase קיים" | לא היה קיים; נוצר היום |
| 2 | `numeric` ל-`ltv_months` ול-`cumulative_profit` | **כל** הערכים הלא-חסרים שלמים ⇒ `integer` (סעיף ד') |
| 3 | `supabase/tests/rls.test.sql` בסגנון pgTAP | דורש `supabase start` ⇒ Docker ⇒ **בלתי אפשרי** |
| 4 | "אותן תוצאות הרשאה מתקבלות דרך שני ה-views" | לא נכון כפי שנוסח: aggregate בלי `group by` מחזיר שורת `NULL` גם למשתמש חסום (סעיף ה') |

### נוסחאות ה-Runtime — שוחזרו מול ה-CSV לפני כתיבת ה-SQL

| נוסחה | תוצאה | מול `SPEC.md` |
|---|---|---|
| נשירה `1 − Σ(stage)/Σ(prev)` על `leads_answered→followup_1..5` | 21.7 / 25.7 / 18.6 / 10.4 / 29.2 | זהה |
| `avg(closed/num_leads)` לשורה, לפי טייר | Low 4.524 (n=780) · Mid 8.220 (n=1,717) · High 5.433 (n=1,003) | זהה |
| שורות בפער 1501–1999 | 0 | תואם |

---

## ג. הכרעות התכנון

**D1 — פרויקט. ✅ בוצע.** `funneliq`, ref `zbxqwcwiirnrfnkzpwri`, אזור
`eu-central-1` — אותו אזור כמו שירות ה-Render (Frankfurt). סיסמת ה-DB שמורה
אצל המשתמש בלבד ותידרש ל-`supabase db push`. **אינה נכנסת ל-`.env` ולא לגיט.**

**D1a — המפתח הציבורי הוא `sb_publishable_…`, לא ה-`anon` הישן.** הפרויקט
נולד עם שתי סדרות מפתחות; Supabase מנפיקה את ה-legacy JWT לתאימות לאחור בלבד.
שניהם ממופים לאותו תפקיד `anon` ⇒ **RLS ו-grants מתנהגים זהה**. ההבדל תפעולי:
רוטציה של ה-legacy מחייבת החלפת ה-JWT secret של הפרויקט, ומפילה איתה את
ה-secret key וכל session פעיל; ה-publishable מתחלף בנפרד.
⚠ `SPEC.md` נוקב ב-"anon key" — תיקון תיעוד ממתין לאישור כפול (סעיף י').

**D2 — טיפוסים, נגזרים ממדידה.** כל 18 העמודות המספריות `integer`.
`ltv_months` ו-`cumulative_profit` nullable; 17 העמודות האחרות `NOT NULL`;
`referred` — `text NOT NULL`. **אין המרה שקטה ואין השלמת חסרים.**

**D3 — `source_row_id`.** `integer NOT NULL UNIQUE`, **1-based**: שורת הנתונים
הראשונה ב-CSV (אחרי הכותרת) = `1`. נגזר דטרמיניסטית מסדר הקובץ, ומשמש כמפתח
ה-upsert — ולכן הוא מה שהופך טעינה חוזרת לבטוחה. `id bigserial primary key`
נשאר כמפתח טכני. הכפילויות העסקיות נשמרות: זהותן אינה נקבעת לפי מפתח זה.

**D4 — grants ו-RLS.** `anon` — אפס הרשאות. `authenticated` — `SELECT` בלבד,
וגם הוא כפוף ל-policy. אין policy ל-`INSERT/UPDATE/DELETE` ⇒ **כתיבה חסומה
לכל משתמש קצה, גם למורשה**. כתיבה רק ב-secret key מהסקריפט המקומי.

⚠ מכיוון ש-**Automatically expose new tables כבוי**, אובייקט חדש ב-`public`
נולד בלי שום grant ואינו נגיש דרך PostgREST עד שמעניקים גישה במפורש. לכן
המיגרציה חייבת לכלול `grant select` נפרד לטבלה **ולכל אחד משני ה-views**.
שכחה תתבטא ב"לא נקרא כלום" — כיוון הכשל הבטוח, וייתפס מיד בבדיקות.

**D5 — שני views.** ראו סעיף ה'.

**D6 — פריסת קבצים.** ה-SQL נשמר ב**עותק יחיד** תחת
`supabase/migrations/<timestamp>_schema.sql` ו-`<timestamp>_views.sql`, כי זה
מה ש-`supabase db push` מריץ. `supabase/config.toml` נכנס לגיט;
`supabase/.temp/` מוחרג. ⚠ עץ הארכיטקטורה ב-`SPEC.md` נוקב ב-`schema.sql`
בשורש — סטייה שדורשת אישור כפול (סעיף י'). **לא ניצור עותק כפול של אותו SQL.**

**D7 — `scripts/load_data.py`.** קורא CSV מקומי · מאמת SHA-256 מול
`8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa` ואת 19
הכותרות · מוסיף `source_row_id` 1-based · `upsert(on_conflict="source_row_id")`
ב-batches של 500 עם secret key מ-`.env` · כשל רועש עם קוד יציאה · בלי הדפסת
env או headers. **אין staging ואין ETL** — הוכרע ביומן ההכרעות.

**D8 — אינדקסים.** אין, מעבר ל-PK ול-`UNIQUE`. 3,500 שורות. `EXPLAIN` על שתי
שאילתות ה-Runtime נשמר כראיה; אינדקס ייווסף רק אם התוכנית תראה צורך אמיתי.

**D9 — בדיקות.** ראו סעיף ו'.

**D10 — secrets.** `.env.example` עם שמות משתנים בלבד: `SUPABASE_URL`,
`SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`. `.env` מוחרג כבר היום.
סריקת secrets לפני כל commit; אין מפתח, JWT, סיסמה או CSV בגיט או בפלט CI.

---

## ד. הסכמה המוצעת

כל טווח ומספר חסרים בטבלה נמדדו היום מול ה-CSV, לא הוערכו.

| עמודה | טיפוס | Null | נמדד |
|---|---|---|---|
| `id` | `bigserial primary key` | לא | מפתח טכני |
| `source_row_id` | `integer not null unique` | לא | 1–3,500 |
| `ad_budget` | `integer not null` | לא | 500–20,000 |
| `num_leads` | `integer not null` | לא | 11–139 |
| `leads_answered` | `integer not null` | לא | 4–84 |
| `leads_not_answered` | `integer not null` | לא | 5–68 |
| `followup_1` … `followup_5` | `integer not null` | לא | 3–66 … 1–27 |
| `not_closed` | `integer not null` | לא | 0–20 |
| `closed` | `integer not null` | לא | 0–9 |
| `calls_to_closed` | `integer not null` | לא | 0–9 |
| `calls_to_not_closed` | `integer not null` | לא | 0–7 |
| `customer_acquisition_cost` | `integer not null` | לא | 0–6,666 |
| `ltv_months` | `integer` | **כן — 4 חסרים** | 1–56, כולם שלמים |
| `purchased` | `integer not null` | לא | 0/1 |
| `upsell` | `integer not null` | לא | 0/1 |
| `cumulative_profit` | `integer` | **כן — 29 חסרים** | 0–149,959, כולם שלמים |
| `referred` | `text not null` | לא | `Yes`/`No` בלבד |

**למה `integer` ולא `numeric`:** שתי עמודות החסרים מופיעות ב-pandas כ-`float64`
**רק** בגלל נוכחות ה-`NaN`. במדידה, כל 3,496 ו-3,471 הערכים הלא-חסרים שלמים,
והמקסימום (149,959) רחוק מגבול `int4`. `numeric` היה יוצר רושם של דיוק עשרוני
שאינו קיים במקור.

**אין `CHECK` מעבר ל-`NOT NULL` המדוד.** constraint שידחה את 155 הרשומות
(`closed > 0` עם `purchased = 0`) או את 333 (`purchased = 0` עם `ltv > 0`)
יסתור את מדיניות שמירת החריגות. הזהויות נאכפות ב-Data Contract, לא ב-DB.

**SQL מוצע:**

```sql
create table public.funnel_records (
  id                        bigserial primary key,
  source_row_id             integer not null unique,
  ad_budget                 integer not null,
  num_leads                 integer not null,
  leads_answered            integer not null,
  leads_not_answered        integer not null,
  followup_1                integer not null,
  followup_2                integer not null,
  followup_3                integer not null,
  followup_4                integer not null,
  followup_5                integer not null,
  not_closed                integer not null,
  closed                    integer not null,
  calls_to_closed           integer not null,
  calls_to_not_closed       integer not null,
  customer_acquisition_cost integer not null,
  ltv_months                integer,
  purchased                 integer not null,
  upsell                    integer not null,
  cumulative_profit         integer,
  referred                  text    not null
);

alter table public.funnel_records enable row level security;

revoke all on public.funnel_records from anon, public;
grant select on public.funnel_records to authenticated;

create policy funnel_records_northbound_select
  on public.funnel_records for select to authenticated
  using (auth.jwt() -> 'app_metadata' ->> 'organization' = 'northbound');
```

`enable row level security` נכתב במפורש ואינו מסתמך על מתג ה-Automatic RLS
בדשבורד, כדי שה-SQL יהיה שחזורי גם על פרויקט שבו המתג כבוי.

---

## ה. שני ה-views

**למה views בכלל.** בלעדיהם כל בקשת תובנה מושכת 3,500 שורות לדפדפן כדי לסכום
אותן שם. `SPEC.md` אוסר stored procedures ושכבת ETL, ו-view הוא הכלי שנשאר:
שורה אחת חוזרת, וה-RLS של טבלת המקור נאכף דרכו כשהוא `security_invoker`.

**סמנטיקת דחייה — הנקודה שהטיוטה פספסה.** aggregate ללא `group by` מחזיר
**תמיד שורה אחת**, גם כשה-RLS סינן את כל השורות — שורה של `NULL`. משתמש חסום
היה מקבל `200 OK` עם תוכן ריק במקום דחייה מובהקת. לכן `followup_insight` מסונן
ב-`where t.n > 0`, ושני ה-views מחזירים **אפס שורות** למשתמש חסום, באותה צורה.

```sql
create view public.followup_insight with (security_invoker = true) as
with t as (
  select count(*)            as n,
         sum(leads_answered) as s0,
         sum(followup_1)     as s1,
         sum(followup_2)     as s2,
         sum(followup_3)     as s3,
         sum(followup_4)     as s4,
         sum(followup_5)     as s5
  from public.funnel_records
)
select v.stage,
       v.from_leads,
       v.to_leads,
       1 - v.to_leads::numeric / nullif(v.from_leads, 0) as drop_rate
from t
cross join lateral (values
  ('followup_1', t.s0, t.s1),
  ('followup_2', t.s1, t.s2),
  ('followup_3', t.s2, t.s3),
  ('followup_4', t.s3, t.s4),
  ('followup_5', t.s4, t.s5)
) as v(stage, from_leads, to_leads)
where t.n > 0;

create view public.budget_tier_insight with (security_invoker = true) as
select case when ad_budget <= 1500                  then 'Low'
            when ad_budget between 2000 and 5000    then 'Mid'
            when ad_budget >  5000                  then 'High' end as budget_tier,
       count(*)                                                     as n_records,
       avg(closed::numeric / nullif(num_leads, 0))                  as conversion_rate
from public.funnel_records
group by 1;

revoke all on public.followup_insight, public.budget_tier_insight from anon, public;
grant select on public.followup_insight, public.budget_tier_insight to authenticated;
```

**הגדרת הטיירים אינה ממציאה טייר לפער 1501–1999.** ערך בפער ייפול ל-`NULL`
ויופיע כשורה נפרדת ב-view — כלומר ה-view **מדווח** על ערך שלא נצפה במקור במקום
לבלוע אותו לתוך Mid. כיום 0 שורות כאלה, וזו בדיקת קבלה.

`budget_tier_insight` מחזיר אפס שורות למשתמש חסום מעצם ה-`group by`, בלי צורך
בסינון נוסף.

---

## ו. סדר ביצוע — 11 checkpoints

| # | פעולה |
|---|---|
| 1 | ✅ **בוצע** — יצירת פרויקט `funneliq` ידנית ואימות `ACTIVE_HEALTHY` |
| 2 | `git switch -c feat/supabase-data` מ-`main` מסונכרן; `supabase init` |
| 3 | כתיבת שתי המיגרציות + `.env.example` + עדכון `.gitignore` |
| 4 | `supabase link` ו-`supabase db push` — סכמה, grants ו-RLS |
| 5 | בדיקות RLS ו-grants **לפני** טעינת נתונים |
| 6 | `load_data.py` — ריצה ראשונה; ספירת שורות |
| 7 | ריצה שנייה — חייבת להישאר 3,500 בדיוק |
| 8 | Data Contract מול Supabase + `EXPLAIN` על שתי שאילתות ה-Runtime |
| 9 | בדיקות RLS מחדש דרך שני ה-views, לאחר שיש נתונים |
| 10 | `pytest` מקומי, סריקת secrets, PR, CI ירוק |
| 11 | תיעוד ראיות במסמך זה, ביקורת, ואישור סגירה נפרד |

### מנגנון בדיקות ה-RLS — בהיעדר Docker

pgTAP מקומי אינו זמין. הבדיקות רצות מול הפרויקט המרוחק בשתי שכבות:

**שכבה 1 — `supabase/tests/rls_checks.sql`** (אינו migration; `select` בלבד,
כל בלוק ב-transaction שנסגר ב-`rollback`):

```sql
begin;  set local role anon;
select count(*) from public.funnel_records;          -- מצופה: permission denied
rollback;

begin;  set local role authenticated;
set local request.jwt.claims = '{"role":"authenticated","app_metadata":{}}';
select count(*) from public.funnel_records;          -- מצופה: 0
select count(*) from public.followup_insight;        -- מצופה: 0 שורות
rollback;

begin;  set local role authenticated;
set local request.jwt.claims =
  '{"role":"authenticated","app_metadata":{"organization":"northbound"}}';
select count(*) from public.funnel_records;          -- מצופה: 3500
insert into public.funnel_records (source_row_id) values (99999);  -- מצופה: דחייה
rollback;
```

`auth.jwt()` ב-Supabase קורא את `request.jwt.claims`, ולכן ההצבה הזו בודקת את
ביטוי ה-policy עצמו. מורץ ב-MCP `execute_sql` באישור, או בהדבקה ב-SQL Editor.

**שכבה 2 — בדיקת `anon` אמיתית ב-HTTP** מול PostgREST עם ה-publishable key,
לטבלה ולשני ה-views. מצופה דחייה אמיתית, לא שורות ריקות. זו הבדיקה שמוכיחה
שהמסלול האמיתי סגור, ולא רק ביטוי ה-policy.

**מה נשאר לפאזה 4:** אימות מקצה-לקצה עם JWT של משתמש אמיתי. פאזה 3 אינה יוצרת
משתמשים ואינה נוגעת בהגדרות ה-Auth.

### `tests/test_data_contract.py`

רץ ב-CI מול ה-CSV בלבד, עם `skipif` כשהקובץ חסר — הוא gitignored, ו-CI חייב
להישאר ירוק בלעדיו. בודק: 3,500×19 · חסרים 4/29 · 19 שורות כפולות ב-9 קבוצות ·
זהויות המשפך · שתי נוסחאות ה-Runtime. **הבדיקות מול Supabase אינן רצות ב-CI**
— אין שם credentials ואסור שיהיו.

---

## ז. קריטריוני קבלה

- בטבלה 3,500 שורות ו-3,500 ערכי `source_row_id` ייחודיים.
- ריצה שנייה של ה-loader אינה משנה את הספירה ואינה מוחקת כפילויות מקור.
- 19 עמודות המקור נשמרות ללא שינוי ערך; 33 הרשומות החסרות נשארות חסרות;
  19 הכפילויות ב-9 הקבוצות נשארות; 155 ו-333 רשומות הקצה נשארות.
- `followup_insight` מחזיר 21.7 / 25.7 / 18.6 / 10.4 / 29.2.
- `budget_tier_insight` מחזיר 4.524 / 8.220 / 5.433 עם n = 780 / 1,717 / 1,003,
  סכום 3,500, ואפס שורות עם `budget_tier is null`.
- `anon` — נדחה בטבלה ובשני ה-views.
- `authenticated` בלי `organization` — אפס שורות בשלושתם.
- `authenticated` עם `organization=northbound` — קורא; כתיבה נדחית גם עבורו.
- CI ירוק גם בלי ה-CSV ובלי credentials.
- אין secret key, JWT, סיסמה, URL פרטי או CSV בגיט או בפלט CI.

---

## ח. ראיות שיישמרו

פלט שתי הרצות ה-loader וספירת שורות אחרי כל אחת · מטריצת RLS עם זהות הבדיקה,
הפעולה, התוצאה הצפויה והתוצאה בפועל · פלט בדיקת ה-`anon` ב-HTTP · פלט
Data Contract מקומי ומול Supabase · `EXPLAIN` לשתי השאילתות וההחלטה המתועדת
על אינדקסים · פלט בדיקת grants, `rowsecurity` ו-`security_invoker` · CI ירוק,
קישור PR ו-SHA של commit הקבלה.

---

## ט. סיכונים ובלמים

| סיכון | בלם |
|---|---|
| secret key עוקף RLS | משמש רק ב-loader מקומי; כל בדיקות ההרשאה נעשות כ-`anon` או כ-`authenticated` |
| View עוקף RLS | `security_invoker = true` + בדיקת דחייה מפורשת דרך כל view |
| דחייה שנראית כהצלחה ריקה | `where t.n > 0` — אפס שורות, לא שורת `NULL` |
| grant חסר בגלל המתג הכבוי | `grant select` מפורש לטבלה ולשני ה-views; ייתפס מיד בבדיקה |
| שינוי נתוני מקור בטעינה | checksum, אימות כותרות והשוואת 19 העמודות |
| loader חלקי | batches עם ספירות, כשל רועש, upsert idempotent |
| טייר מומצא לפער 1501–1999 | `case` ללא ענף `else`; ערך בפער מדווח כ-`NULL` ונבדק |
| סימולציית claims אינה המסלול האמיתי | נוספת בדיקת `anon` אמיתית ב-HTTP; JWT אמיתי בפאזה 4 |
| דליפת secrets בלוגים | אין הדפסת env/headers; סריקת repo לפני PR |

---

## י. מה מסמך זה **אינו** מאשר

אינו אישור להריץ SQL על הפרויקט, להשתמש ב-secret key, ליצור משתמשים, לגעת
בהגדרות Auth, לפתוח branch, לבצע commit או PR, או להתחיל את ביצוע פאזה 3.
אלה מתחילים רק לאחר ביקורת ואישור סופי מפורש, לפי שער המעבר.

**שלושה תיקוני `SPEC.md` ממתינים לאישור כפול נפרד:**

1. שורה 22 — "**קיים:** GitHub, פרויקט Supabase" לא היה נכון במועד הכתיבה.
2. עץ הארכיטקטורה — `schema.sql` בשורש מול `supabase/migrations/` בפועל (D6).
3. מטריצת ההרשאות — "anon key בלבד" → publishable key (D1a). המהות אינה
   משתנה: מפתח ציבורי בלבד, לעולם לא ה-secret key.
