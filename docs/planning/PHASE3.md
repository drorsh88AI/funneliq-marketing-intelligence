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

⚠ **הערכים בטבלה מוצגים כאחוזים, אך היחידה הקנונית היא יחס 0–1.** ה-views
מחזירים `0.21741…`, לא `21.7`. ראו סעיף ה'. המוסכמה תיכנס לחוזה ה-API בפאזה 8.

---

## ג. הכרעות התכנון

**D1 — פרויקט. ✅ בוצע.** `funneliq`, ref `zbxqwcwiirnrfnkzpwri`, אזור
`eu-central-1` — אותו אזור כמו שירות ה-Render (Frankfurt). סיסמת ה-DB שמורה
אצל המשתמש בלבד ותידרש ל-`supabase db push`. **אינה נכנסת ל-`.env` ולא לגיט.**

**D1a — המפתח הציבורי הוא `sb_publishable_…`, לא ה-`anon` הישן.** הפרויקט
נולד עם שתי סדרות מפתחות; Supabase מנפיקה את ה-legacy JWT לתאימות לאחור בלבד.
שניהם ממופים לאותו תפקיד `anon` ⇒ **RLS ו-grants מתנהגים זהה**.
*(✅ `SPEC.md` עודכן בהתאם 01.09.2026 — ראו §י.)*

ההבדל הוא תפעולי, ויש לנסח אותו במדויק. המפתחות החדשים **אינם מבוססי JWT**
ומנוהלים בנפרד מה-JWT signing key; לפי תיעוד Supabase יצירתם *"adds them
alongside your existing anon and service_role keys without affecting them"*.
רוטציית ה-JWT secret הישן משפיעה על **מפתחות `anon`/`service_role` הישנים ועל
ה-JWTs והסשנים החתומים באותו secret** — ו**אינה** מבטלת מפתח `sb_secret` חדש.
היתרון בבחירה: מפתח חדש שדלף מבוטל פרטנית, בעוד שביטול מפתח legacy מחייב
רוטציה שגוררת איתה את הזוג השני ואת הטוקנים.

*(תיקון: ניסוח קודם במסמך זה טען שרוטציית ה-legacy "מפילה את ה-secret key".
זה היה שגוי — sb_secret אינו נגזר מה-JWT secret.)*

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
`supabase/.temp/` מוחרג. ✅ עץ הארכיטקטורה ב-`SPEC.md` עודכן בהתאם 01.09.2026
(סעיף י'). **לא נוצר עותק כפול של אותו SQL.**

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

revoke all    on public.funnel_records from anon, authenticated, public;
grant  select on public.funnel_records to   authenticated;

create policy funnel_records_northbound_select
  on public.funnel_records for select to authenticated
  using (auth.jwt() -> 'app_metadata' ->> 'organization' = 'northbound');
```

`enable row level security` נכתב במפורש ואינו מסתמך על מתג ה-Automatic RLS
בדשבורד, כדי שה-SQL יהיה שחזורי גם על פרויקט שבו המתג כבוי.

**ה-`revoke` כולל את `authenticated` במפורש, וזה לא ייתור.** הניסוח המתבקש
(`from anon, public`) אינו מבטל הרשאות שכבר ניתנו ל-`authenticated`, ולכן הוא
מסתמך על כך ש-Automatically-expose כבוי דווקא בפרויקט הזה. עם `revoke` מלא
ואחריו `grant select`, **מצב ההרשאות הסופי נקבע על ידי המיגרציה** ולא יורש
מהגדרת הפרויקט — ומטריצת הבדיקה בסעיף ו' מוכיחה מצב שנקבע, לא מצב מקרי.
הסדר מהותי: `revoke` קודם, `grant` אחריו.

---

## ה. שני ה-views

**למה views בכלל.** בלעדיהם כל בקשת תובנה מושכת 3,500 שורות לדפדפן כדי לסכום
אותן שם. `SPEC.md` אוסר stored procedures ושכבת ETL, ו-view הוא הכלי שנשאר:
שורה אחת חוזרת, וה-RLS של טבלת המקור נאכף דרכו כשהוא `security_invoker`.

**סמנטיקת דחייה — הנקודה שהטיוטה פספסה.** aggregate ללא `group by` מחזיר
**תמיד שורה אחת**, גם כשה-RLS סינן את כל השורות — שורה של `NULL`. משתמש חסום
היה מקבל `200 OK` עם תוכן ריק במקום דחייה מובהקת. לכן `followup_insight` מסונן
ב-`having count(*) > 0`, ושני ה-views מחזירים **אפס שורות** למשתמש חסום, באותה
צורה.

**היחידה היא יחס בטווח 0–1, לא אחוז.** ה-views מחזירים `0.21741…`, ולא `21.7`.
המרה לאחוזים היא **שכבת התצוגה בלבד** — עקבי עם ההפרדה שכבר קיימת באפיון בין
אחסון/שליפה לבין הצגה. לכן גם קריטריוני הקבלה (סעיף ז') מנוסחים כיחס עם
סובלנות מספרית, ולא כשוויון למספר מעוגל. ⚠ המוסכמה הזו חייבת להיכנס לחוזה
ה-API בפאזה 8.

**סדר השורות מפורש, ואינו נסמך על סדר ההחזרה.** SQL אינו מבטיח סדר בלי
`order by`, ו-view אינו יכול לכפות אותו על הצרכן. בלי עמודת סדר, מיון אלפביתי
של הטיירים ייתן **High, Low, Mid** — גרף שגוי שנראה תקין. לכן שני ה-views
מחזירים עמודת סדר מפורשת: `stage_order` ו-`tier_order`.

```sql
create view public.followup_insight with (security_invoker = true) as
    select 1 as stage_order, 'followup_1' as stage,
           sum(leads_answered) as from_leads, sum(followup_1) as to_leads,
           1 - sum(followup_1)::numeric / nullif(sum(leads_answered), 0) as drop_rate
    from public.funnel_records having count(*) > 0
  union all
    select 2, 'followup_2', sum(followup_1), sum(followup_2),
           1 - sum(followup_2)::numeric / nullif(sum(followup_1), 0)
    from public.funnel_records having count(*) > 0
  union all
    select 3, 'followup_3', sum(followup_2), sum(followup_3),
           1 - sum(followup_3)::numeric / nullif(sum(followup_2), 0)
    from public.funnel_records having count(*) > 0
  union all
    select 4, 'followup_4', sum(followup_3), sum(followup_4),
           1 - sum(followup_4)::numeric / nullif(sum(followup_3), 0)
    from public.funnel_records having count(*) > 0
  union all
    select 5, 'followup_5', sum(followup_4), sum(followup_5),
           1 - sum(followup_5)::numeric / nullif(sum(followup_4), 0)
    from public.funnel_records having count(*) > 0;

create view public.budget_tier_insight with (security_invoker = true) as
select case when ad_budget <= 1500               then 1
            when ad_budget between 2000 and 5000 then 2
            when ad_budget >  5000               then 3    end as tier_order,
       case when ad_budget <= 1500               then 'Low'
            when ad_budget between 2000 and 5000 then 'Mid'
            when ad_budget >  5000               then 'High' end as budget_tier,
       count(*)                                    as n_records,
       avg(closed::numeric / nullif(num_leads, 0)) as conversion_rate
from public.funnel_records
group by 1, 2;

revoke all    on   public.followup_insight, public.budget_tier_insight
              from anon, authenticated, public;
grant  select on   public.followup_insight, public.budget_tier_insight
              to   authenticated;
```

**על צורת ה-`union all`.** גם `cross join lateral (values …)` תקין ב-PostgreSQL
והיה עובד. הבחירה כאן היא **קריאוּת בלבד** — חמישה `select` זהים במבנה שכל אחד
מהם מובן בפני עצמו. חמש סריקות על 3,500 שורות אינן שיקול ביצועים לכאן ולכאן.
ה-`revoke` כולל את `authenticated` מאותה סיבה שהוסברה בסעיף ד'.

**הגדרת הטיירים אינה ממציאה טייר לפער 1501–1999.** ערך בפער ייפול ל-`NULL`
ויופיע כשורה נפרדת ב-view — כלומר ה-view **מדווח** על ערך שלא נצפה במקור במקום
לבלוע אותו לתוך Mid. כיום 0 שורות כאלה, וזו בדיקת קבלה.

`budget_tier_insight` מחזיר אפס שורות למשתמש חסום מעצם ה-`group by`, בלי צורך
בסינון נוסף.

---

## ו. סדר ביצוע — 11 checkpoints

| # | פעולה |
|---|---|
| 1 | בדיקת פתיחה: `main` מסונכרן, עץ עבודה נקי, פרויקט Supabase זמין ומאומת |
| 2 | `git switch -c feat/supabase-data` מ-`main` מסונכרן; `supabase init` |
| 3 | כתיבת שתי המיגרציות + `.env.example` + עדכון `.gitignore` |
| 4 | `supabase link` ו-`supabase db push` — סכמה, grants ו-RLS |
| 5 | **שכבות A + B + E** — grants, דגלי אובייקטים ובדיקת `anon` ב-HTTP, לפני טעינה |
| 6 | `load_data.py` — ריצה ראשונה; ספירת שורות |
| 7 | ריצה שנייה — חייבת להישאר 3,500 בדיוק |
| 8 | Data Contract מול Supabase, בדיקת parity ו-`EXPLAIN` על שתי שאילתות ה-Runtime |
| 9 | **שכבות C + D**, וחזרה על E — אכיפת RLS וניסיונות כתיבה, לאחר שיש נתונים |
| 10 | `pytest` מקומי, סריקת secrets, PR, CI ירוק |
| 11 | תיעוד ראיות במסמך זה, ביקורת, ואישור סגירה נפרד |

⚠ **יצירת פרויקט Supabase אינה ברשימה הזו בכוונה.** היא בוצעה בתוך **שער
המעבר 2→3**, כחלק מבדיקת המצב בפועל, ולפי `SPEC.md` השער "אינו נספר באחוז
השלמת הביצוע". מלוא הראיה נשמר בסעיף ב' וב-`note` של הפאזה ב-`ROADMAP.html`.
זה גם ההבדל מפאזה 2, שבה פתיחת חשבון Render **כן** הייתה תת-משימת ביצוע —
שם היא בוצעה אחרי אישור התכנון ובתוך הביצוע.

### מנגנון בדיקות ה-RLS — חמש שכבות, בהיעדר Docker

pgTAP מקומי אינו זמין. **העיקרון המנחה:** לבדוק הרשאות דרך פונקציות קטלוג
שמחזירות `boolean`, ולא דרך עוררות שגיאות. שגיאה מבטלת transaction וגוררת את
שאר הסקריפט; `false` לא. בנוסף, יש להבחין בין שני מצבי דחייה שונים לחלוטין:

| מצב | ביטוי |
|---|---|
| **אין `grant`** | שגיאה — `permission denied` |
| יש `grant`, ה-RLS מסנן | **אפס שורות**, בלי שגיאה |

הבדיקות אינן רשאיות לערבב ביניהם. הקובץ: `supabase/tests/rls_checks.sql` —
**אינו migration**.

**שכבה A — מטריצת grants** (checkpoint 5; אינה תלויה בנתונים):

```sql
select r.rolname, o.obj, p.priv,
       has_table_privilege(r.rolname, o.obj, p.priv) as actual,
       (r.rolname = 'authenticated' and p.priv = 'SELECT') as expected,
       has_table_privilege(r.rolname, o.obj, p.priv)
         = (r.rolname = 'authenticated' and p.priv = 'SELECT') as pass
from   (values ('anon'),('authenticated')) as r(rolname)
cross join (values ('public.funnel_records'),
                   ('public.followup_insight'),
                   ('public.budget_tier_insight')) as o(obj)
cross join (values ('SELECT'),('INSERT'),('UPDATE'),('DELETE')) as p(priv);
```

2 תפקידים × 3 אובייקטים × 4 פעולות = **24 שורות**, כל אחת עם `pass` מפורש.
הקבלה: 24/24 `true`. זו ההוכחה שמצב ההרשאות הוא מה שהמיגרציה קבעה. נשמר גם
פלט `relacl` הגולמי משלושת האובייקטים.

**שכבה B — דגלי אובייקטים** (checkpoint 5): `relrowsecurity` על הטבלה, ו-
`reloptions` המכיל `security_invoker=true` על שני ה-views, מתוך `pg_class`.
⚠ הצורה המדויקת של `reloptions` תאומת בהרצה — הבדיקה מדפיסה את הערך הגולמי
לצד ה-`pass`, כדי שלא תיפול על הבדל ניסוח.

**שכבה C — ספירות שורות תחת claims מדומים** (checkpoint 9, **אחרי** הטעינה).
כל מצב הוא בלוק `begin … rollback` אחד שמחזיר שורה אחת עם שלוש ספירות:

| מצב | טבלה | `followup_insight` | `budget_tier_insight` |
|---|---|---|---|
| `authenticated`, בלי `organization` | 0 | 0 | 0 |
| `authenticated`, `organization=northbound` | 3,500 | 5 | 3 |

```sql
begin;
set local role authenticated;
set local request.jwt.claims =
  '{"role":"authenticated","app_metadata":{"organization":"northbound"}}';
select 'northbound' as state,
       (select count(*) from public.funnel_records)      as rows_table,
       (select count(*) from public.followup_insight)    as rows_followup,
       (select count(*) from public.budget_tier_insight) as rows_tiers;
rollback;
```

`auth.jwt()` ב-Supabase קורא את `request.jwt.claims`, ולכן ההצבה בודקת את ביטוי
ה-policy עצמו. **חובה להחליף תפקיד** — הרצה כבעלים תראה 3,500 בכל מקרה, כי RLS
אינו חל על בעל הטבלה, והבדיקה תהיה חסרת ערך.

**שכבה D — ניסיונות כתיבה כשגיאות אמיתיות** (checkpoint 9). כל אחת **בקריאה
נפרדת**, כי היא מבטלת את ה-transaction. שלושתן כזהות Northbound:

- `INSERT` — עם **כל 17 עמודות ה-`NOT NULL` מלאות**. זה קריטי: `INSERT` חסר
  עמודות עלול להיכשל על `NOT NULL` ולהיראות כ"נחסם" גם אם ה-grant ניתן בטעות
  — **false pass**. (Postgres אמנם בודק ACL לפני constraints, אבל הבדיקה לא
  תסתמך על סדר פנימי שאינו חלק מהחוזה.)
- `update public.funnel_records set ad_budget = ad_budget where source_row_id = 1;`
- `delete from public.funnel_records where source_row_id = 1;`

מצופה `permission denied` בשלושתן. שכבה D היא **אישוש** למסלול האמיתי; שכבה A
היא ההוכחה.

**שכבה E — דחיית `anon` אמיתית, בשני המסלולים** (checkpoints 5 ו-9). שכבה A
מוכיחה את ה-ACL מהקטלוג; שכבה E מאששת שההתנהגות בפועל תואמת.

**E1 — SQL.** שלוש קריאות **מבודדות**, כל אחת בקריאה משלה כי כל אחת מבטלת את
ה-transaction:

```sql
begin; set local role anon;
select count(*) from public.funnel_records;      -- מצופה: 42501
rollback;
```

ובאותה צורה ל-`public.followup_insight` ול-`public.budget_tier_insight`. נשמרים
קוד השגיאה `42501` וההודעה המלאה, כמו בשכבה D.

**E2 — HTTP.** `GET` לטבלה ולשני ה-views, ו-`POST` אחד, מול PostgREST עם
ה-publishable key ב-`apikey`. מצופה דחייה אמיתית, לא שורות ריקות.

שתי התת-שכבות רצות גם **לפני** הטעינה — `anon` נדחה ללא תלות בנתונים. E2 היא
הבדיקה שמוכיחה שהמסלול שהמשתמש באמת עובר בו סגור.

#### נוהל ניקוי אחרי בדיקות שגיאה (D ו-E1)

שש הבדיקות שמעוררות שגיאה במכוון — שלוש בשכבה D ושלוש ב-E1 — מותירות את
ה-transaction במצב **aborted**. Postgres דוחה כל פקודה נוספת עד `ROLLBACK`,
ולכן `rollback` שנכתב **בתוך אותו בלוק** אחרי השגיאה אינו מובטח שירוץ. ב-SQL
Editor, שבו הסשן נשמר בין הרצות, מצב aborted נדבק — והשגיאה של **הבדיקה
הבאה** תיראה כתוצאת RLS במקום כשארית של הבדיקה הקודמת.

**ההכרעה: אפשרות א׳ — SQL Editor, אותו session.** שש בדיקות השגיאה עוברות
מ-MCP ל-SQL Editor, כל בדיקה ונוהל הניקוי שלה **באותו חלון/session**. MCP
נשאר המסלול הראשי לשכבות A/B/C בלבד, שאינן מעוררות שגיאות.

*(אפשרות שנדחתה: `exception handler` ב-PL/pgSQL שתופס `insufficient_privilege`
בתוך הבלוק עצמו, כך שה-transaction החיצוני אינו נשאר aborted. נדחתה כקסם
מיותר בשביל שש בדיקות; ר' סעיף ד' לנוהל המעבר אליה אם session affinity נכשל.)*

**הרצף לכל בדיקת שגיאה — שישה שלבים:**

| # | פקודה | מצופה |
|---|---|---|
| 1 | `select pg_backend_pid();` | נרשם כזהות ה-session |
| 2 | ניסיון השגיאה (שכבה D או E1) | `42501` + ההודעה המלאה |
| 3 | `rollback;` | ה-transaction נסגר |
| 4 | `reset role;` | — |
| 5 | `reset request.jwt.claims;` | — |
| 6 | אימות מצב | ארבע שורות `pass = true` |

**שאילתת האימות — ארבע בדיקות עם `expected`/`actual`/`pass` מפורשים:**

```sql
select 'same_pid' as check_name,
       '<PID_FROM_STEP_1>'    as expected,
       pg_backend_pid()::text as actual,
       pg_backend_pid() = <PID_FROM_STEP_1> as pass
union all
select 'current_user_equals_session_user',
       session_user::text, current_user::text,
       current_user = session_user
union all
select 'role_reset',
       'none', coalesce(current_setting('role', true), '<null>'),
       coalesce(current_setting('role', true), 'none') = 'none'
union all
select 'claims_safe',
       'NULL or valid JSON',
       coalesce(current_setting('request.jwt.claims', true), '<null>'),
       current_setting('request.jwt.claims', true) is null
         or pg_input_is_valid(current_setting('request.jwt.claims', true), 'jsonb');
```

**שלוש נקודות שיש להקפיד עליהן בניסוח:**

- **בעלות החיבור אינה נגזרת מ-`current_setting('role')`.** אחרי `RESET ROLE`
  ה-GUC חוזר ל-`none`, וזה **מצב תקין**; הבדיקה הנכונה לחזרה לבעל החיבור היא
  `current_user = session_user`.
- **`claims_safe` אינו דורש ניסוח פנימי מסוים** — `NULL` תקין, וכל JSON תקף
  תקין. אין להיתלות בערך ברירת מחדל ספציפי ש-`RESET` יחזיר.
- הבדיקה משתמשת ב-`pg_input_is_valid` (PG 16+; הפרויקט על 17.6) כדי **לא**
  לזרוק בעצמה — cast ישיר ל-`jsonb` על ערך פגום היה מבטל את ה-transaction
  ומייצר בדיוק את הבעיה שהנוהל בא למנוע.

**ארבעה כללים:**

1. אין להתחיל את הבדיקה הבאה לפני שהאימות בשלב 6 חזר כמצופה בכל ארבע השורות.
2. **הראיה כוללת את פלט האימות**, לא רק את השגיאה — בלעדיו אי אפשר לדעת
   ששגיאת ההמשך אינה שארית של הבדיקה הקודמת.
3. **לעולם לא `set_config` למחרוזת ריקה** על `request.jwt.claims`. רק `RESET`.
4. ⚠ **הנחת ה-session חייבת להיבדק, לא להיות מונחת.** הבדיקה הראשונה, פעם
   אחת לפני שש בדיקות השגיאה, מוודאת ש-SQL Editor אכן שומר session בין
   הרצות. אם ה-`pid` משתנה — אין session affinity גם שם, כל הנוהל אינו תקף,
   ויש לעבור לחלופת ה-exception handler.

#### ממשל הבדיקות — מי מריץ ואיך נשמרת הראיה

| כלל | קיבוע |
|---|---|
| יחידת הרצה | **A/B/C:** כל בלוק `begin…rollback` מורץ כיחידה אחת ואינו מפוצל. **D/E1:** ניסיון השגיאה ונוהל הניקוי הם קריאות נפרדות באותו SQL Editor session; לאחר הניקוי מורצת שאילתת האימות, ואין להתחיל בדיקה נוספת לפני שכל ארבעת ערכי `pass` הם `true` |
| מסלול — שכבות A/B/C | **MCP `execute_sql` ראשי · SQL Editor גיבוי** — אותו טקסט SQL בשני המסלולים. אינן מעוררות שגיאה, ולכן אינן תלויות ב-session affinity |
| מסלול — שכבות D/E1 | **חובה SQL Editor, כל בדיקה ונוהל הניקוי שלה באותו session.** ⚠ **אסור** MCP: שתי קריאות MCP נפרדות (בדיקה + ניקוי) אינן מובטחות ליפול על אותו חיבור מה-pool, וקריאת ניקוי על חיבור אחר נותנת ביטחון שווא. ראו "נוהל ניקוי אחרי בדיקות שגיאה" למטה |
| פלט כל שכבה | נשמר כטבלה עם שלוש עמודות חובה: `expected`, `actual`, `pass` |
| שכבות D ו-E1 | נשמרות בנפרד, עם **קוד השגיאה והודעת PostgreSQL המלאה** (`42501` · `permission denied for table …`) — לא כ-`pass` בוליאני בלבד. כל בדיקה מלווה בפלט נוהל הניקוי |
| שכבה E2 | נשמרים **status code** וגוף תגובה מסונן. **בלי headers** ובלי echo של הבקשה |
| מפתחות | **אף בדיקה אינה מדפיסה את ה-publishable key**, גם שהוא ציבורי. הוא מוזכר כשם משתנה בלבד |

**מה נשאר לפאזה 4:** אימות מקצה-לקצה עם JWT של משתמש אמיתי. פאזה 3 אינה יוצרת
משתמשים ואינה נוגעת בהגדרות ה-Auth.

### `tests/test_data_contract.py`

רץ ב-CI מול ה-CSV בלבד, עם `skipif` כשהקובץ חסר — הוא gitignored, ו-CI חייב
להישאר ירוק בלעדיו. בודק: 3,500×19 · חסרים 4/29 · 19 שורות כפולות ב-9 קבוצות ·
זהויות המשפך · שתי נוסחאות ה-Runtime. **הבדיקות מול Supabase אינן רצות ב-CI**
— אין שם credentials ואסור שיהיו.

**בדיקת ה-parity — בעלות מפורשת.** ההשוואה בין ערכי ה-views לערכים שמחשב
Python מה-CSV **אינה** בדיקת CI, כי ה-views דורשים credentials. היא צעד מקומי
ב-**checkpoint 8**: שולפים את שני ה-views, מריצים את אותן נוסחאות על ה-CSV,
ומשווים בסובלנות `1e-9`. בלי ההצמדה הזו, "parity" הוא קריטריון בלי בעלים.

---

## ז. קריטריוני קבלה

- בטבלה 3,500 שורות ו-3,500 ערכי `source_row_id` ייחודיים.
- ריצה שנייה של ה-loader אינה משנה את הספירה ואינה מוחקת כפילויות מקור.
- 19 עמודות המקור נשמרות ללא שינוי ערך; 33 הרשומות החסרות נשארות חסרות;
  19 הכפילויות ב-9 הקבוצות נשארות; 155 ו-333 רשומות הקצה נשארות.
- **מיפוי מלא, לא רק ספירה:** לכל `k` בין 1 ל-3,500, השורה שבה
  `source_row_id = k` זהה בכל 19 העמודות לשורת הנתונים ה-`k` ב-CSV. השוואה
  מלאה, לא מדגם. *(בלי הקריטריון הזה, טעינה שערבבה את הסדר עוברת את כל
  היתר.)*
- **ערכי שני ה-views זהים לערכים שמחשב Python מה-CSV, בהפרש מוחלט קטן מ-
  `1e-9`.** היחידה היא יחס 0–1. הערכים המעוגלים — נשירה 21.7 / 25.7 / 18.6 /
  10.4 / 29.2 אחוז, וטיירים 4.524 / 8.220 / 5.433 אחוז — הם **אינפורמטיביים
  בלבד** ואינם תנאי השוואה.
- `budget_tier_insight` מחזיר n = 780 / 1,717 / 1,003, סכום 3,500, ואפס שורות
  עם `budget_tier is null`.
- שני ה-views מחזירים `stage_order` 1–5 ו-`tier_order` 1–3 בהתאמה.
- **מטריצת ה-grants: 24 מתוך 24 `pass`.**
- `anon` — נדחה בשגיאה בטבלה ובשני ה-views: `42501` בשלוש קריאות SQL (E1)
  ודחייה ב-HTTP (E2).
- `authenticated` בלי `organization` — **אפס שורות** בשלושתם, בלי שגיאה.
- `authenticated` עם `organization=northbound` — 3,500 / 5 / 3; שלושת ניסיונות
  הכתיבה נדחים ב-`permission denied`.
- CI ירוק גם בלי ה-CSV ובלי credentials.
- אין secret key, JWT, סיסמה או CSV בגיט או בפלט CI. **הבדיקה מקובעת** —
  חיפוש צורת מפתח אמיתי, לא אזכור של מונח:

  **שתי פקודות נפרדות** — `git grep` סורק את עץ העבודה בלבד ואינו קורא
  היסטוריה, ולכן אינו יכול "לרוץ על `git log -p`":

  ```sh
  # 1. עץ העבודה
  git grep -nE 'sb_secret_[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}'

  # 2. היסטוריית ה-branch  (grep -nE חלופי אם rg אינו ב-PATH)
  git log -p main..HEAD | rg -n 'sb_secret_[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}'
  ```

  שתיהן חייבות לחזור ריקות. ⚠ המילים `service_role`,
  `SUPABASE_SECRET_KEY`, או `sb_secret_…` עם אליפסיס — **אינן ממצא**. אם
  הסריקה מסמנת את מסמכי התכנון עצמם, הרגקס שגוי ולא המסמכים.

---

## ח. ראיות שיישמרו

פלט חמש שכבות הבדיקה, כל אחת כטבלה עם `expected` / `actual` / `pass` לפי כללי
הממשל בסעיף ו':

| שכבה | מה נשמר |
|---|---|
| A | 24 שורות מטריצת ה-grants + פלט `relacl` גולמי משלושת האובייקטים |
| B | `relrowsecurity` ו-`reloptions` הגולמי של שני ה-views |
| C | ספירות שלושת האובייקטים בשני מצבי המשתמש |
| D | שלוש שגיאות הכתיבה, **עם קוד `42501` וההודעה המלאה** + פלט אימות הניקוי (`pid`/`role`/`claims`) אחרי כל אחת |
| E1 | שלוש שגיאות ה-`anon` ב-SQL — טבלה ושני views — עם `42501` וההודעה המלאה + פלט אימות הניקוי אחרי כל אחת |
| E2 | status code וגוף מסונן לכל קריאת HTTP; **בלי headers ובלי מפתחות** |

בנוסף: פלט שתי הרצות ה-loader וספירת שורות אחרי כל אחת · פלט Data Contract
מקומי ומול Supabase · תוצאת בדיקת ה-parity בסובלנות `1e-9` · `EXPLAIN` לשתי
השאילתות וההחלטה המתועדת על אינדקסים · פלט סריקת ה-secrets · CI ירוק, קישור PR
ו-SHA של commit הקבלה.

---

## ט. סיכונים ובלמים

| סיכון | בלם |
|---|---|
| secret key עוקף RLS | משמש רק ב-loader מקומי; כל בדיקות ההרשאה נעשות כ-`anon` או כ-`authenticated` |
| View עוקף RLS | `security_invoker = true` + בדיקת דחייה מפורשת דרך כל view |
| דחייה שנראית כהצלחה ריקה | `having count(*) > 0` — אפס שורות, לא שורת `NULL` |
| grant חסר בגלל המתג הכבוי | `grant select` מפורש לטבלה ולשני ה-views; ייתפס מיד בבדיקה |
| **הרשאה עודפת ל-`authenticated` ששרדה** כי ה-`revoke` לא כלל אותו | `revoke all … from anon, authenticated, public` לפני ה-`grant`; מטריצה A מאמתת 24/24 |
| **false pass ב-`INSERT`** — כשל על `NOT NULL` שנראה כחסימת הרשאות | ה-`INSERT` בשכבה D מספק את כל 17 עמודות ה-`NOT NULL`; שכבה A היא ההוכחה העיקרית |
| **גרף מטעה בהיעדר סדר** — מיון אלפביתי ייתן High, Low, Mid | `stage_order` ו-`tier_order` מפורשים בשני ה-views |
| **בדיקת RLS חסרת ערך** כי רצה כבעל הטבלה | חובה `set local role authenticated`; RLS אינו חל על הבעלים |
| שינוי נתוני מקור בטעינה | checksum, אימות כותרות והשוואת 19 העמודות |
| loader חלקי | batches עם ספירות, כשל רועש, upsert idempotent |
| טייר מומצא לפער 1501–1999 | `case` ללא ענף `else`; ערך בפער מדווח כ-`NULL` ונבדק |
| סימולציית claims אינה המסלול האמיתי | נוספת בדיקת `anon` אמיתית ב-HTTP; JWT אמיתי בפאזה 4 |
| דליפת secrets בלוגים | אין הדפסת env/headers; סריקת repo לפני PR |
| **שגיאת המשך שנקראת בטעות כתוצאת RLS** — transaction נשאר aborted אחרי שגיאת D/E1 ומזהם את הבדיקה הבאה | נוהל ניקוי ייעודי (§ו): `rollback`/`reset role`/`reset request.jwt.claims` באותו session ב-SQL Editor, עם אימות `pid`/`role`/`claims` לפני כל בדיקה |
| **`request.jwt.claims` שנותר לא-JSON ושובר את `auth.jwt()`** | לעולם לא `set_config(..., '', false)`; רק `RESET`, מאומת ב-`pg_input_is_valid` |

---

## י. מה מסמך זה **אינו** מאשר

אינו אישור להריץ SQL על הפרויקט, להשתמש ב-secret key, ליצור משתמשים, לגעת
בהגדרות Auth, לפתוח branch, לבצע commit או PR, או להתחיל את ביצוע פאזה 3.
אלה מתחילים רק לאחר ביקורת ואישור סופי מפורש, לפי שער המעבר.

**✅ תיקוני `SPEC.md` הוחלו 01.09.2026**, לאחר אישור כפול נפרד (ראו
`docs/planning/codex-review.md`, יומן ההכרעות):

1. שורה 3 ("מצב: אפיון בלבד") ושורה 22 ("קיים: פרויקט Supabase") — תוקנו.
2. עץ הארכיטקטורה — `schema.sql` בשורש הוחלף ב-`supabase/migrations/` (D6).
3. מטריצת ההרשאות — "anon key בלבד" הוחלף ב-publishable key (D1a). המהות
   לא השתנתה: מפתח ציבורי בלבד, לעולם לא ה-secret key.
4. פסקת "מצב נוכחי" — מתוארכת ומצביעה ל-`ROADMAP.html` כמקור החי.

---

## יא. הוראת ביצוע — שער `2→3` נסגר

**⚠ מסמך זה הוא ההוראה הפורמלית. הוא אינו מפעיל את הביצוע.** ביצוע בפועל —
פתיחת branch, SQL, Supabase — מתחיל רק בפקודת התחלה נפרדת ומפורשת.

**שרשרת האישור:**

| שלב | ראיה |
|---|---|
| תכנון מפורט מחדש על בסיס מצב מאומת | סעיפים א'–י' לעיל |
| שלושה סבבי ביקורת Codex–Claude | תוקנו: יחידת ה-view, חמש שכבות RLS, checkpoint 1, נוסח רוטציית מפתחות, בדיקת `anon` חסרה, שורה כפולה ביומן, נוהל ניקוי |
| מיזוג מסמכי התכנון ל-`main` | PR #11, commit `dd051b5`, CI ירוק |
| תיקוני `SPEC.md` (סעיף י') | הוחלו באותו מיזוג |
| אישור סופי: `planning_status → approved_for_execution` | commit `02ea94c`, ישירות ל-`main`, CI ירוק |

**מה מאושר לביצוע, ברגע שתינתן פקודת התחלה:** 11 ה-checkpoints בסעיף ו',
בסדר הזה, על `branch feat/supabase-data`. קריטריוני הקבלה — סעיף ז'.
הראיות הנדרשות לכל שכבה — סעיף ח'.

**מה עדיין אינו מאושר, גם אחרי פקודת התחלה, בלי אישור נפרד:** שינוי ב-`SPEC.md`
מעבר לארבעת התיקונים שכבר הוחלו · יצירת משתמשי Auth (פאזה 4) · מיזוג ה-branch
ל-`main` בסוף — checkpoint 11 עצמו דורש "ביקורת ואישור סגירה נפרד".

**זה אינו הוראה להתחיל.** `execution_status` נשאר `not_started` עד שתינתן
פקודה מפורשת נוספת.
