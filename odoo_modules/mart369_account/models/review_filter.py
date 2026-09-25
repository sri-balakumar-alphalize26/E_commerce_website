"""Holding a review back until staff have looked at it.

A review goes live at once unless it carries something a shop should not
publish unread:

* a phone number (seven digits or more, however they are spaced) - reviews are
  public, and a number in one is either the author's own or somebody else's;
* a link or an e-mail address - the usual shape of spam;
* an abusive word, from the list below or from Settings > Reviews.

The list covers the languages 369 Mart's customers write in - English, Tamil,
Malayalam, Telugu, Urdu/Hindi and Arabic - in their own script and in the Latin
spellings people type on a phone ("thevdiya", "bhenchod"). It is a starting
point, not a promise: no list of bad words is ever complete, which is why staff
can add to it, and why a held review is only held, never deleted.

Matching is done on a normalised copy of the text: lower case, accents off,
common look-alikes turned back into letters (@ -> a, 0 -> o, $ -> s ...), and
runs of the same letter squeezed ("fuuuck" -> "fuck"). Latin-script words must
match a whole word, so "Scunthorpe" and "assessment" pass; words in other
scripts match anywhere, because those scripts do not put spaces where English
does.
"""

import re
import unicodedata

# --------------------------------------------------------------- the words
#
# Kept short and unambiguous on purpose: a word that is also an everyday word
# ("dog", "cow" in several languages) would hold half the reviews in the shop.

WORDS = {
    'en': [
        'fuck', 'fucker', 'fucking', 'motherfucker', 'shit', 'bullshit', 'bitch', 'bastard',
        'asshole', 'arsehole', 'dick', 'dickhead', 'cunt', 'wanker', 'slut', 'whore',
        'prick', 'twat', 'bollocks', 'retard', 'nigger', 'nigga', 'faggot', 'fag',
    ],
    # Tamil
    'ta': [
        'thevdiya', 'thevidiya', 'thevudiya', 'thevadiya', 'otha', 'ommala', 'oombu',
        'punda', 'pundai', 'sunni', 'koothi', 'baadu', 'loosu koothi',
        'naaye', 'porukki', 'saniyan', 'thayoli', 'mayiru',
        'தேவடியா', 'ஓத்தா', 'ஒம்மால', 'ஊம்பு', 'புண்ட', 'சுன்னி', 'கூதி', 'பாடு',
        'தாயோளி', 'மயிரு', 'பொறுக்கி',
    ],
    # Malayalam
    'ml': [
        'myre', 'myran', 'mairan', 'poorimone', 'poori', 'thayoli', 'kunna', 'kunne',
        'pundachi', 'koothichi', 'thendi', 'naari', 'polayadi',
        'മൈരെ', 'മൈരൻ', 'പൂറിമോനെ', 'പൂറി', 'തായോളി', 'കുണ്ണ', 'പുണ്ടച്ചി',
        'കൂതിച്ചി', 'തെണ്ടി', 'നാറി', 'പൊലയാടി',
    ],
    # Telugu
    'te': [
        'dengu', 'dengey', 'lanja', 'lanjakodaka', 'modda', 'puku', 'gudda', 'kojja',
        'bokka', 'erripuka', 'dongamunda',
        'దెంగు', 'లంజ', 'లంజకొడక', 'మొడ్డ', 'పూకు', 'గుద్ద', 'కొజ్జ', 'బొక్క',
    ],
    # Urdu / Hindi (Latin and both scripts)
    'ur': [
        'chutiya', 'chutia', 'madarchod', 'maderchod', 'behenchod', 'bhenchod', 'bhosdike',
        'bhosdiwale', 'gandu', 'randi', 'harami', 'haramzada', 'kutta', 'kamina', 'lund',
        'gaand', 'chod',
        'چوتیا', 'مادرچود', 'بہنچود', 'گانڈو', 'رنڈی', 'حرامی', 'حرامزادہ', 'کمینہ',
        'चूतिया', 'मादरचोद', 'बहनचोद', 'भोसडीके', 'गांडू', 'रंडी', 'हरामी', 'कमीना',
    ],
    # Arabic (Oman / Gulf)
    'ar': [
        'kalb', 'ibn el kalb', 'sharmoota', 'sharmouta', 'kos', 'kuss', 'khara',
        'zibbi', 'manyak', 'hmar', 'ya hayawan',
        'ابن الكلب', 'شرموطة', 'خرا', 'منيوك', 'قحبة',
    ],
}

# The look-alikes people use to slip a word past a filter.
LEET = str.maketrans({'@': 'a', '4': 'a', '3': 'e', '1': 'i', '!': 'i', '0': 'o',
                      '$': 's', '5': 's', '7': 't', '+': 't', '|': 'i'})

PHONE = re.compile(r'(?:\+?\d[\s\-().]*){7,}')
LINK = re.compile(r'(https?://|www\.|\b[\w.-]+\.(com|in|net|org|me|co|om|shop|xyz|info|link)\b'
                  r'|[\w.+-]+@[\w-]+\.[\w.]+)', re.IGNORECASE)


def _is_latin(word):
    return all(ord(ch) < 0x250 for ch in word if ch.isalpha())


def normalise(text):
    """The text as the filter reads it."""
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)
                   or not _is_latin(ch))
    text = text.lower().translate(LEET)
    # "fuuuuck" -> "fuck", "shiiit" -> "shit"; two of a letter are kept.
    return re.sub(r'(.)\1{2,}', r'\1\1', text)


def _squeeze(text):
    return re.sub(r'(.)\1+', r'\1', text)


def _pattern(word):
    """A whole-word pattern where any vowel may be hidden behind a * ("f*ck")."""
    body = ''.join('[%s*]' % ch if ch in 'aeiou' else re.escape(ch) for ch in word)
    return r'(?<![a-z*])' + body + r'(?![a-z*])'


def blocked_words(extra=None):
    """Every word the filter holds for: the built-in list and staff's own."""
    words = [w for group in WORDS.values() for w in group]
    words += [w.strip() for w in (extra or '').splitlines() if w.strip()]
    return sorted({normalise(w) for w in words if w})


def check(title, text, extra_words=None):
    """[reason] for holding a review back; [] when it can go live."""
    raw = ' '.join(p for p in (title, text) if p)
    reasons = []
    if PHONE.search(raw):
        reasons.append('phone number')
    if LINK.search(raw):
        reasons.append('link or e-mail')
    plain = normalise(raw)
    squeezed = _squeeze(plain)
    for word in blocked_words(extra_words):
        if _is_latin(word):
            if re.search(_pattern(word), plain) or re.search(_pattern(_squeeze(word)), squeezed):
                reasons.append('abusive words')
                break
        elif word in plain:
            reasons.append('abusive words')
            break
    return reasons
