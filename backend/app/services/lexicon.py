"""Multilingual extraction lexicon.

Every entry maps a canonical value to the surface phrases that indicate it,
across English, romanised Indic and native scripts. Because all languages are
matched simultaneously, code-switched utterances ("mujhe mechanical kaam
pasand hai") are handled without a separate path.

Skill phrases deliberately live in the database (SkillAlias) rather than here -
the taxonomy is the single source of truth for skills. This file covers the
slots the taxonomy does not: education, mobility, goals, constraints and
occupation.
"""

from __future__ import annotations

from ..core.enums import EducationLevel, GoalType, Mobility

# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------
# Ordered most-specific first: "12th" must be tested before "10th" cannot match
# it, and "iti" before generic "diploma".

EDUCATION_PHRASES: list[tuple[str, tuple[str, ...]]] = [
    (
        EducationLevel.POSTGRADUATE,
        ("post graduate", "postgraduate", "master degree", "masters", "m a ", "m sc", "m com",
         "mba", "एमए", "स्नातकोत्तर", "முதுகலை"),
    ),
    (
        EducationLevel.GRADUATE,
        ("graduate", "graduation", "degree college", "bachelor", "b a ", "b sc", "b com",
         "b tech", "be degree", "स्नातक", "ग्रेजुएट", "डिग्री", "पदवी", "இளநிலை", "பட்டப்படிப்பு"),
    ),
    (
        EducationLevel.DIPLOMA,
        ("diploma", "polytechnic", "डिप्लोमा", "पॉलिटेक्निक", "டிப்லோமா"),
    ),
    (
        EducationLevel.ITI,
        ("iti", "i t i", "industrial training institute", "trade certificate", "आईटीआई",
         "व्यावसायिक प्रशिक्षण", "ஐடிஐ"),
    ),
    (
        EducationLevel.CLASS_12,
        ("12th", "12 th", "class 12", "twelfth", "higher secondary", "hsc", "intermediate",
         "puc", "12 pass", "barahvi", "barhvi", "बारहवीं", "१२वीं", "12वीं", "बारावी",
         "பன்னிரண்டாம்", "பிளஸ் டூ"),
    ),
    (
        EducationLevel.CLASS_10,
        ("10th", "10 th", "class 10", "tenth", "matric", "matriculation", "sslc", "ssc",
         "10 pass", "10th pass", "dasvi", "dasveen", "das pass", "दसवीं", "१०वीं", "10वीं",
         "दहावी", "मैट्रिक", "பத்தாம் வகுப்பு", "பத்தாவது", "పదవ తరగతి"),
    ),
    (
        EducationLevel.CLASS_8,
        ("8th", "8 th", "class 8", "eighth", "8 pass", "aathvi", "आठवीं", "८वीं", "8वीं",
         "आठवी", "எட்டாம் வகுப்பு"),
    ),
    (
        EducationLevel.PRIMARY,
        ("5th", "class 5", "primary school", "fifth", "प्राथमिक", "पांचवीं", "५वीं",
         "தொடக்கப்பள்ளி"),
    ),
    (
        EducationLevel.NONE,
        ("never went to school", "no schooling", "not studied", "did not study", "illiterate",
         "स्कूल नहीं", "पढ़ा नहीं", "अनपढ़", "शाळेत गेलो नाही", "படிக்கவில்லை"),
    ),
]

# ---------------------------------------------------------------------------
# Occupation
# ---------------------------------------------------------------------------

OCCUPATION_PHRASES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "Agriculture / farm work",
        "Agriculture",
        ("farming", "farmer", "agriculture", "agricultural", "i farm", "crop", "field work",
         "kheti", "khet", "kisan", "shetkari", "shetat", "खेती", "किसान", "कृषि", "खेत",
         "शेती", "शेतकरी", "விவசாயம்", "விவசாயி", "వ్యవసాయం", "কৃষি"),
    ),
    (
        "Agricultural labour",
        "Agriculture",
        ("farm labour", "farm labourer", "agricultural labour", "majdoori", "mazdoor",
         "मजदूरी", "मजदूर", "कूली", "கூலி வேலை"),
    ),
    (
        "Dairy / livestock",
        "Agriculture",
        ("dairy", "milk business", "cattle", "buffalo", "goat rearing", "पशुपालन", "दूध",
         "डेयरी", "பால் பொருள்"),
    ),
    (
        "Machinery repair / mechanic",
        "Engineering",
        ("mechanic", "repair work", "repairing", "garage", "workshop", "मैकेनिक", "मरम्मत",
         "गैराज", "दुरुस्ती", "மெக்கானிக்", "ரிப்பேர்"),
    ),
    (
        "Construction work",
        "Construction",
        ("construction", "mason", "mistri", "building work", "राजमिस्त्री", "मिस्त्री",
         "निर्माण", "கட்டுமான"),
    ),
    (
        "Driving",
        "Logistics",
        ("driver", "driving", "auto rickshaw", "tempo", "ड्राइवर", "ड्राइविंग", "ஓட்டுநர்"),
    ),
    (
        "Tailoring",
        "Apparel",
        ("tailor", "tailoring", "stitching", "सिलाई", "दर्जी", "தையல்"),
    ),
    (
        "Shop / small trade",
        "Retail",
        ("shop", "shopkeeper", "small business", "dukan", "दुकान", "व्यापार", "கடை"),
    ),
    (
        "Software engineer / developer",
        "IT & Software",
        ("software engineer", "software developer", "software", "developer", "programmer",
         "coder", "coding", "web developer", "app developer", "computer engineer",
         "it engineer", "engineer", "engineering", "सॉफ्टवेयर इंजीनियर", "डेवलपर", "कोडिंग",
         "மென்பொருள் பொறியாளர்", "సాఫ్ట్‌వేర్ ఇంజనీర్"),
    ),
    (
        "IT support / computer technician",
        "IT & Software",
        ("it support", "computer technician", "hardware engineer", "hardware support",
         "network technician", "system admin", "pc repair", "कंप्यूटर ऑपरेटर", "आईटी"),
    ),
    (
        "Data analyst / Office associate",
        "IT & Software",
        ("data analyst", "data entry", "office assistant", "excel operator",
         "computer operator", "डाटा एंट्री"),
    ),
    (
        "Mechanical / Civil engineer",
        "Engineering",
        ("mechanical engineer", "civil engineer", "cad engineer", "site engineer",
         "diploma engineer", "मैकेनिकल इंजीनियर", "सिविल इंजीनियर"),
    ),
    (
        "Accountant / Finance executive",
        "Finance",
        ("accountant", "accounting", "tally operator", "finance executive", "bookkeeper",
         "मुनीम", "अकाउंटेंट"),
    ),
    (
        "Currently not working",
        None,
        ("no work", "unemployed", "not working", "jobless", "sitting at home", "बेरोजगार",
         "काम नहीं", "वेळ नाही काम", "வேலை இல்லை"),
    ),
]

# ---------------------------------------------------------------------------
# Mobility
# ---------------------------------------------------------------------------

MOBILITY_PHRASES: dict[str, tuple[str, ...]] = {
    Mobility.LOW: (
        "cannot travel", "can not travel", "cant travel", "can't travel", "not travel far",
        "cannot go far", "cannot go very far", "unable to travel", "no travel",
        "near my village", "near my home", "close to home", "nearby only", "only nearby",
        "in my village", "same village", "stay here", "within village", "walking distance",
        "door nahi", "dur nahi ja sakta", "gaon me hi", "gaon mein hi", "bahar nahi",
        "दूर नहीं", "दूर नहीं जा सकता", "गाँव में ही", "गांव में ही", "बाहर नहीं जा सकता",
        "घर के पास", "दूर जाना मुश्किल", "लांब जाऊ शकत नाही", "गावातच",
        "தூரம் போக முடியாது", "வெளியே போக முடியாது", "ஊரிலேயே", "దూరం వెళ్లలేను",
    ),
    Mobility.HIGH: (
        "can travel anywhere", "travel anywhere", "ready to travel", "willing to travel",
        "can relocate", "ready to relocate", "willing to relocate", "shift to city",
        "go to city", "any city", "anywhere in state", "no problem travelling",
        "kahin bhi ja sakta", "kahin bhi", "shahar ja sakta",
        "कहीं भी जा सकता", "कहीं भी जाने को तैयार", "शहर जा सकता", "दूर जा सकता",
        "कुठेही जाऊ शकतो", "எங்கும் போக முடியும்", "வெளியூர் போகலாம்",
    ),
    Mobility.MEDIUM: (
        "can travel a little", "travel some distance", "nearby town", "taluka", "block level",
        "up to some distance", "daily up down", "can go to town", "thoda door",
        "थोड़ा दूर", "आस पास", "तालुका", "जवळपास", "கொஞ்சம் தூரம்",
    ),
}

# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

GOAL_PHRASES: dict[str, tuple[str, ...]] = {
    GoalType.SELF_EMPLOYMENT: (
        "own business", "my own work", "own shop", "start my own", "self employment",
        "self employed", "be my own boss", "own workshop", "own garage", "start a business",
        "apna kaam", "apna business", "apni dukan", "khud ka kaam",
        "अपना काम", "अपना व्यवसाय", "अपनी दुकान", "खुद का काम", "स्वयंरोजगार",
        "स्वतःचा व्यवसाय", "சொந்த தொழில்", "சொந்தமாக", "సొంత వ్యాపారం",
    ),
    GoalType.JOB: (
        "want a job", "need a job", "looking for job", "get employment", "naukri",
        "company job", "permanent job", "salary job",
        "नौकरी", "नौकरी चाहिए", "काम चाहिए", "नोकरी", "வேலை வேண்டும்", "ఉద్యోగం",
    ),
    GoalType.APPRENTICESHIP: (
        "apprentice", "apprenticeship", "learn on the job", "learn while working",
        "प्रशिक्षु", "अप्रेंटिस", "शिकाऊ", "பயிற்சி பணி",
    ),
    GoalType.TRAINING: (
        "want to learn", "want training", "learn new skill", "get certificate",
        "certification", "course", "training chahiye", "sikhna hai",
        "सीखना है", "प्रशिक्षण", "कोर्स", "सर्टिफिकेट", "शिकायचे आहे",
        "கற்க வேண்டும்", "பயிற்சி", "నేర్చుకోవాలి",
    ),
    GoalType.HIGHER_INCOME: (
        "earn more", "more income", "more money", "better income", "increase income",
        "higher income", "improve earning", "income badhana", "zyada kamana",
        "jyada paisa", "paisa kamana",
        "ज्यादा कमाना", "ज्यादा पैसा", "अधिक आय", "कमाई बढ़ाना", "आय बढ़ाना",
        "जास्त कमवायचे", "अधिक उत्पन्न", "அதிக வருமானம்", "நல்ல சம்பளம்",
        "ఎక్కువ సంపాదించాలి",
    ),
}

# ---------------------------------------------------------------------------
# Interests (canonical tag -> phrases). Tags match skill taxonomy codes where
# one exists, so an interest can be scored against an opportunity's skills.
# ---------------------------------------------------------------------------

INTEREST_PHRASES: dict[str, tuple[str, ...]] = {
    "mechanical": (
        "mechanical", "machine work", "machines", "engine work", "repair work", "technical work",
        "mechanic work", "machine ka kaam", "मशीन का काम", "मशीन", "यंत्र", "तांत्रिक काम",
        "मेकॅनिकल", "மெக்கானிக்", "இயந்திர வேலை", "మెకానికల్",
    ),
    "electrical": (
        "electrical", "electric work", "wiring", "electrician", "बिजली का काम", "बिजली",
        "वायरिंग", "மின் வேலை",
    ),
    "agriculture": (
        "agriculture", "farming interest", "crop", "खेती", "कृषि", "शेती", "விவசாயம்",
    ),
    "enterprise": (
        "business", "trading", "shop", "व्यवसाय", "व्यापार", "தொழில்",
    ),
    "computers": (
        "computer", "mobile repair", "digital", "कंप्यूटर", "मोबाइल", "கணினி",
    ),
    "driving": ("driving", "vehicle", "ड्राइविंग", "गाड़ी", "ஓட்டுநர்"),
    "tailoring": ("tailoring", "stitching", "सिलाई", "தையல்"),
    "construction": ("construction", "building", "निर्माण", "கட்டுமான"),
}

# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

CONSTRAINT_PHRASES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "travel",
        "Cannot travel long distances",
        ("cannot travel", "cannot go far", "no vehicle", "no bus", "door nahi ja sakta",
         "दूर नहीं जा सकता", "गाड़ी नहीं", "बस नहीं", "லாரி இல்லை", "தூரம் போக முடியாது"),
    ),
    (
        "financial",
        "Cannot afford course fees",
        ("no money for fees", "cannot pay fees", "fees problem", "free course only",
         "paisa nahi", "फीस नहीं दे सकता", "पैसे नहीं", "मोफत", "கட்டணம் கட்ட முடியாது"),
    ),
    (
        "time",
        "Limited time availability",
        ("only part time", "part time", "few hours only", "busy in farm season",
         "season me busy", "समय नहीं", "सीजन में व्यस्त", "நேரம் இல்லை"),
    ),
    (
        "family",
        "Family responsibilities",
        ("family responsibility", "look after family", "children to look after",
         "parents are old", "परिवार की जिम्मेदारी", "घर देखना", "குடும்ப பொறுப்பு"),
    ),
    (
        "physical",
        "Physical limitation",
        ("back pain", "cannot lift heavy", "health problem", "disability", "injured",
         "कमर दर्द", "भारी नहीं उठा सकता", "बीमारी", "உடல் நலம்"),
    ),
    (
        "language",
        "Prefers regional language instruction",
        ("english nahi", "no english", "only hindi", "only marathi", "only tamil",
         "अंग्रेजी नहीं", "इंग्लिश नहीं आती", "मराठीत", "தமிழில் மட்டும்"),
    ),
    (
        "digital_access",
        "Limited smartphone or internet access",
        ("no smartphone", "no internet", "network problem", "phone nahi",
         "मोबाइल नहीं", "इंटरनेट नहीं", "நெட்வொர்க் இல்லை"),
    ),
]

# ---------------------------------------------------------------------------
# Experience / duration cues
# ---------------------------------------------------------------------------

YEAR_UNITS = ("year", "years", "saal", "sal", "varsh", "साल", "वर्ष", "वर्षे", "ஆண்டு", "வருடம்")
MONTH_UNITS = ("month", "months", "mahina", "mahine", "महीना", "महीने", "महिने", "மாதம்")

#: Phrases that indicate occasional rather than continuous practice, which
#: caps the proficiency we are willing to infer.
OCCASIONAL_CUES = (
    "sometimes", "occasionally", "now and then", "once in a while", "kabhi kabhi",
    "कभी कभी", "कधी कधी", "சில நேரம்", "அப்போது",
)

#: Phrases indicating sustained/daily practice.
REGULAR_CUES = (
    "daily", "every day", "regularly", "full time", "always", "roz", "hamesha",
    "रोज", "हमेशा", "रोजच", "தினமும்", "எப்போதும்",
)

#: Phrases that mark a formally verified claim rather than a self report.
CERTIFICATION_CUES = (
    "certificate", "certified", "iti pass", "trade test", "diploma in",
    "सर्टिफिकेट", "प्रमाणपत्र", "சான்றிதழ்",
)


def all_phrases_for_language_check() -> int:
    """Count of lexicon entries. Used by tests to guard against accidental loss."""
    return (
        sum(len(p) for _, p in EDUCATION_PHRASES)
        + sum(len(p) for _, _, p in OCCUPATION_PHRASES)
        + sum(len(p) for p in MOBILITY_PHRASES.values())
        + sum(len(p) for p in GOAL_PHRASES.values())
        + sum(len(p) for p in INTEREST_PHRASES.values())
        + sum(len(p) for _, _, p in CONSTRAINT_PHRASES)
    )
