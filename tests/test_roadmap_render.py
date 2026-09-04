"""ROADMAP.html מרונדר דרך innerHTML — טקסט מהנתונים חייב escaping.

הבאג שנתפס כאן: ראיית checkpoint 11 בפאזה 5 מכילה את המחרוזת הטכנית
"<title>/<desc>". בלי escaping הדפדפן מפרש אותה כתג פתיחה, מעביר את הפרסר
ל-RCDATA, ובולע את כל שאר כרטיס הפאזה — checkpoints 12-14, מד ההתקדמות,
בדיקת הקבלה ותיבת השער — אף שכולם קיימים במערך PHASES.

ponytail: בדיקת מקור, לא רינדור אמיתי — אין DOM parser בסביבה בלי להוסיף
תלות (jsdom/lxml). היא תופסת את מחלקת הרגרסיה האמיתית (שדה נתונים שמוזרק
ל-innerHTML בלי esc). אם תתווסף אי-פעם תלות עם פרסר HTML אמיתי, אפשר
לשדרג לבדיקת DOM שסופרת <li> בפועל.
"""
import re
from pathlib import Path

ROADMAP = Path(__file__).resolve().parents[1] / "ROADMAP.html"


def _source() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def _phase5_block(src: str) -> str:
    start = src.index('num:5, name:')
    end = src.index('num:6, name:', start)
    return src[start:end]


def test_phase5_still_contains_the_raw_html_string_that_triggered_the_bug():
    """שומר על אי-ריקנות של הבדיקות שאחריה: אם המחרוזת תיעלם מהנתונים,
    הבדיקות למטה עדיין יעברו אבל כבר לא יבדקו כלום — וזה יתגלה כאן."""
    assert "<title>/<desc>" in _phase5_block(_source())


def test_phase5_has_all_fourteen_checkpoints_in_the_data():
    block = _phase5_block(_source())
    numbers = [int(m) for m in re.findall(r'\{t:"checkpoint (\d+) —', block)]
    assert numbers == list(range(1, 15)), numbers


def test_no_phases_field_is_interpolated_into_innerhtml_without_escaping():
    """כל הזרקה ישרה של שדה מ-PHASES לתבנית — ${it.e} וכדומה — אסורה; חייב
    ${esc(it.e)}. תגיות שה-renderer עצמו מייצר אינן נוגעות לכאן.

    ponytail: תופס הזרקה ישירה בלבד, לא ביטוי מורכב שמחזיר טקסט מהנתונים
    (${it.e ? ... : ...}) — אלה תנאים, והערך בתוכם נבדק כאן ממילא כשהוא מוזרק.
    """
    raw = re.findall(
        r"\$\{\s*(?:it\.\w+|itemText\([^)]*\)|p\.note|p\.name|p\.branch"
        r"|p\.accept\.\w+|next\.name|d)\s*\}",
        _source(),
    )
    assert raw == [], raw


def test_esc_helper_covers_the_four_characters_that_matter():
    src = _source()
    fn = src[src.index("function esc(s)"):src.index("function itemText")]
    for ch in ("&", "<", ">", '"'):
        assert f"'{ch}'" in fn, ch
