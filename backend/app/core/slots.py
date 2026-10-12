"""Conversation slot configuration.

The adaptive conversation is driven entirely by this table - which facts matter,
in what order, and how to ask for each one in each language. Nothing here is
hardcoded in the frontend: the client renders whatever question the server
returns. Adding a language or reordering the conversation is a change to this
file alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import GoalType, Mobility


@dataclass
class SlotOption:
    value: str
    labels: dict[str, str]
    icon: str | None = None

    def label_for(self, language: str) -> str:
        return self.labels.get(language) or self.labels.get("en", self.value)


@dataclass
class SlotDefinition:
    name: str
    #: Lower runs first. High-value facts are asked about before nice-to-haves.
    priority: int
    required: bool
    #: free_text | choice | location
    input_type: str
    questions: dict[str, str]
    #: Asked only when this other slot is already filled (e.g. ask how long they
    #: have been repairing pumps only after they mention repairing pumps).
    depends_on: str | None = None
    options: list[SlotOption] = field(default_factory=list)
    help_text: dict[str, str] = field(default_factory=dict)
    #: The same question built around what the person already said, e.g.
    #: "How long have you been doing pump repair?". `{topic}` is filled in.
    topic_questions: dict[str, str] = field(default_factory=dict)
    #: A sample answer, offered when an answer was not understood.
    examples: dict[str, str] = field(default_factory=dict)
    #: False for slots that are recorded when volunteered but never asked for.
    proactive: bool = True

    def question_for(self, language: str, topic: str | None = None) -> str:
        if topic and language in self.topic_questions:
            return self.topic_questions[language].format(topic=topic)
        return self.questions.get(language) or self.questions["en"]

    def help_for(self, language: str) -> str | None:
        return self.help_text.get(language) or self.help_text.get("en")

    def example_for(self, language: str) -> str | None:
        return self.examples.get(language) or self.examples.get("en")


MOBILITY_OPTIONS = [
    SlotOption(
        Mobility.LOW,
        {
            "en": "Only near my village",
            "hi": "सिर्फ़ अपने गाँव के पास",
            "kn": "ನನ್ನ ಊರಿನ ಹತ್ತಿರ ಮಾತ್ರ",
            "mr": "फक्त माझ्या गावाजवळ",
            "ta": "என் ஊருக்கு அருகில் மட்டும்",
            "te": "నా ఊరి దగ్గర మాత్రమే",
            "bn": "শুধু আমার গ্রামের কাছে",
        },
        icon="home",
    ),
    SlotOption(
        Mobility.MEDIUM,
        {
            "en": "I can go to the nearby town",
            "hi": "मैं पास के कस्बे तक जा सकता हूँ",
            "kn": "ಹತ್ತಿರದ ಪಟ್ಟಣಕ್ಕೆ ಹೋಗಬಲ್ಲೆ",
            "mr": "मी जवळच्या शहरात जाऊ शकतो",
            "ta": "அருகில் உள்ள ஊருக்கு போக முடியும்",
            "te": "దగ్గరి పట్టణానికి వెళ్లగలను",
            "bn": "কাছের শহরে যেতে পারি",
        },
        icon="bus",
    ),
    SlotOption(
        Mobility.HIGH,
        {
            "en": "I can travel further or move",
            "hi": "मैं दूर जा सकता हूँ या शिफ़्ट हो सकता हूँ",
            "kn": "ದೂರ ಹೋಗಬಲ್ಲೆ ಅಥವಾ ಸ್ಥಳಾಂತರವಾಗಬಲ್ಲೆ",
            "mr": "मी लांब जाऊ शकतो किंवा स्थलांतर करू शकतो",
            "ta": "தூரம் பயணிக்க அல்லது இடம் மாற முடியும்",
            "te": "దూరం వెళ్లగలను లేదా మారగలను",
            "bn": "দূরে যেতে বা স্থানান্তর করতে পারি",
        },
        icon="train",
    ),
]

GOAL_OPTIONS = [
    SlotOption(
        GoalType.JOB,
        {
            "en": "A job with an employer",
            "hi": "किसी के यहाँ नौकरी",
            "kn": "ಯಾರದಾದರೂ ಬಳಿ ಉದ್ಯೋಗ",
            "mr": "नोकरी",
            "ta": "ஒரு வேலை",
            "te": "ఉద్యోగం",
            "bn": "একটি চাকরি",
        },
        icon="briefcase",
    ),
    SlotOption(
        GoalType.APPRENTICESHIP,
        {
            "en": "Learn while working (apprenticeship)",
            "hi": "काम करते हुए सीखना",
            "kn": "ಕೆಲಸ ಮಾಡುತ್ತಾ ಕಲಿಯುವುದು",
            "mr": "काम करत शिकणे",
            "ta": "வேலை செய்து கற்க",
            "te": "పని చేస్తూ నేర్చుకోవడం",
            "bn": "কাজ করে শেখা",
        },
        icon="tools",
    ),
    SlotOption(
        GoalType.SELF_EMPLOYMENT,
        {
            "en": "Start my own work",
            "hi": "अपना काम शुरू करना",
            "kn": "ನನ್ನದೇ ಸ್ವಂತ ಕೆಲಸ ಶುರು ಮಾಡುವುದು",
            "mr": "स्वतःचा व्यवसाय सुरू करणे",
            "ta": "சொந்தத் தொழில் தொடங்க",
            "te": "సొంత పని ప్రారంభించడం",
            "bn": "নিজের কাজ শুরু করা",
        },
        icon="shop",
    ),
    SlotOption(
        GoalType.TRAINING,
        {
            "en": "Training and a certificate first",
            "hi": "पहले प्रशिक्षण और प्रमाणपत्र",
            "kn": "ಮೊದಲು ತರಬೇತಿ ಮತ್ತು ಪ್ರಮಾಣಪತ್ರ",
            "mr": "आधी प्रशिक्षण आणि प्रमाणपत्र",
            "ta": "முதலில் பயிற்சி மற்றும் சான்றிதழ்",
            "te": "ముందు శిక్షణ మరియు సర్టిఫికేట్",
            "bn": "প্রথমে প্রশিক্ষণ ও সার্টিফিকেট",
        },
        icon="certificate",
    ),
]

EDUCATION_OPTIONS = [
    SlotOption("none", {"en": "I did not go to school", "hi": "मैं स्कूल नहीं गया", "kn": "ನಾನು ಶಾಲೆಗೆ ಹೋಗಿಲ್ಲ", "mr": "मी शाळेत गेलो नाही", "ta": "பள்ளி செல்லவில்லை"}),
    SlotOption("class_8", {"en": "Up to 8th standard", "hi": "आठवीं तक", "kn": "8ನೇ ತರಗತಿಯವರೆಗೆ", "mr": "आठवीपर्यंत", "ta": "8ஆம் வகுப்பு வரை"}),
    SlotOption("class_10", {"en": "10th standard", "hi": "दसवीं", "kn": "10ನೇ ತರಗತಿ (SSLC)", "mr": "दहावी", "ta": "10ஆம் வகுப்பு"}),
    SlotOption("class_12", {"en": "12th standard", "hi": "बारहवीं", "kn": "12ನೇ ತರಗತಿ (PUC)", "mr": "बारावी", "ta": "12ஆம் வகுப்பு"}),
    SlotOption("iti", {"en": "ITI", "hi": "आईटीआई", "kn": "ಐಟಿಐ", "mr": "आयटीआय", "ta": "ஐடிஐ"}),
    SlotOption("diploma", {"en": "Diploma", "hi": "डिप्लोमा", "kn": "ಡಿಪ್ಲೊಮಾ", "mr": "डिप्लोमा", "ta": "டிப்ளோமா"}),
    SlotOption("graduate", {"en": "Graduate", "hi": "स्नातक", "kn": "ಪದವಿ", "mr": "पदवीधर", "ta": "பட்டப்படிப்பு"}),
]


SLOT_DEFINITIONS: list[SlotDefinition] = [
    SlotDefinition(
        name="occupation",
        priority=10,
        required=True,
        input_type="free_text",
        questions={
            "en": "What kind of work do you currently do?",
            "hi": "अभी आप क्या काम करते हैं?",
            "kn": "ನೀವು ಈಗ ಯಾವ ಕೆಲಸ ಮಾಡುತ್ತೀರಿ?",
            "mr": "सध्या तुम्ही कोणते काम करता?",
            "ta": "இப்போது நீங்கள் என்ன வேலை செய்கிறீர்கள்?",
            "te": "ఇప్పుడు మీరు ఏ పని చేస్తున్నారు?",
            "bn": "এখন আপনি কী কাজ করেন?",
        },
        help_text={"en": "Speak normally. For example: I work on my farm and repair pumps."},
        examples={
            "en": "“I work on my farm and repair pumps.”",
            "hi": "“मैं खेती करता हूँ और पंप ठीक करता हूँ।”",
            "kn": "“ನಾನು ಕೃಷಿ ಮಾಡುತ್ತೇನೆ ಮತ್ತು ಪಂಪ್ ರಿಪೇರಿ ಮಾಡುತ್ತೇನೆ.”",
        },
    ),
    SlotDefinition(
        name="skills",
        priority=20,
        required=True,
        input_type="free_text",
        questions={
            "en": "What tasks or skills are you most comfortable doing?",
            "hi": "आप कौन सा काम पहले से अच्छे से कर लेते हैं?",
            "kn": "ನೀವು ಯಾವ ಕೆಲಸಗಳನ್ನು ಚೆನ್ನಾಗಿ ಮಾಡಬಲ್ಲಿರಿ?",
            "mr": "तुम्हाला कोणते काम आधीपासून चांगले जमते?",
            "ta": "எந்த வேலையை உங்களால் ஏற்கனவே நன்றாக செய்ய முடியும்?",
            "te": "మీరు ఇప్పటికే బాగా చేయగల పని ఏది?",
            "bn": "কোন কাজ আপনি আগে থেকেই ভালো পারেন?",
        },
        topic_questions={"en": "Besides {topic}, what tasks or skills are you comfortable doing?"},
        examples={
            "en": "“I repair pumps and drive a tractor.”",
            "hi": "“मैं पंप ठीक करता हूँ और ट्रैक्टर चलाता हूँ।”",
            "kn": "“ನಾನು ಪಂಪ್ ರಿಪೇರಿ ಮಾಡುತ್ತೇನೆ ಮತ್ತು ಟ್ರ್ಯಾಕ್ಟರ್ ಓಡಿಸುತ್ತೇನೆ.”",
        },
    ),
    SlotDefinition(
        name="experience",
        priority=30,
        required=False,
        depends_on="skills",
        input_type="free_text",
        questions={
            "en": "How long have you been doing this work?",
            "hi": "आप यह काम कब से कर रहे हैं?",
            "kn": "ನೀವು ಈ ಕೆಲಸವನ್ನು ಎಷ್ಟು ಸಮಯದಿಂದ ಮಾಡುತ್ತಿದ್ದೀರಿ?",
            "mr": "तुम्ही हे काम किती काळापासून करत आहात?",
            "ta": "இந்த வேலையை எவ்வளவு காலமாக செய்கிறீர்கள்?",
            "te": "ఈ పని ఎంతకాలం నుండి చేస్తున్నారు?",
            "bn": "কতদিন ধরে এই কাজ করছেন?",
        },
        topic_questions={"en": "How long have you been doing {topic}?"},
        examples={
            "en": "“For five years.”",
            "hi": "“पाँच साल से।”",
            "kn": "“ಐದು ವರ್ಷಗಳಿಂದ.”",
        },
    ),
    SlotDefinition(
        name="education",
        priority=40,
        required=True,
        input_type="choice",
        options=EDUCATION_OPTIONS,
        questions={
            "en": "What is the highest level of education you completed?",
            "hi": "आपने कहाँ तक पढ़ाई की है?",
            "kn": "ನೀವು ಎಲ್ಲಿಯವರೆಗೆ ಓದಿದ್ದೀರಿ?",
            "mr": "तुमचे शिक्षण किती झाले आहे?",
            "ta": "நீங்கள் எவ்வளவு படித்திருக்கிறீர்கள்?",
            "te": "మీరు ఎంతవరకు చదివారు?",
            "bn": "আপনি কতদূর পড়াশোনা করেছেন?",
        },
        help_text={
            "en": "This decides which training and jobs you are eligible for.",
            "hi": "इससे तय होता है कि आप किस प्रशिक्षण और नौकरी के योग्य हैं।",
            "kn": "ನೀವು ಯಾವ ತರಬೇತಿ ಮತ್ತು ಉದ್ಯೋಗಗಳಿಗೆ ಅರ್ಹರು ಎಂಬುದನ್ನು ಇದು ನಿರ್ಧರಿಸುತ್ತದೆ.",
        },
        examples={
            "en": "“I studied up to 10th standard.”",
            "hi": "“मैंने दसवीं तक पढ़ाई की है।”",
            "kn": "“ನಾನು ಹತ್ತನೇ ತರಗತಿಯವರೆಗೆ ಓದಿದ್ದೇನೆ.”",
        },
    ),
    SlotDefinition(
        name="goal",
        priority=50,
        required=True,
        input_type="choice",
        options=GOAL_OPTIONS,
        questions={
            "en": "What kind of work would you like in the future - a job, training, or starting your own work?",
            "hi": "आगे आप क्या चाहते हैं - नौकरी, काम के साथ सीखना, प्रशिक्षण, या अपना काम?",
            "kn": "ಮುಂದೆ ನೀವು ಏನು ಮಾಡಲು ಬಯಸುತ್ತೀರಿ - ಉದ್ಯೋಗ, ತರಬೇತಿ, ಅಥವಾ ನಿಮ್ಮದೇ ಸ್ವಂತ ಕೆಲಸ?",
            "mr": "पुढे तुम्हाला काय हवे - नोकरी, काम करत शिकणे, प्रशिक्षण, की स्वतःचा व्यवसाय?",
            "ta": "அடுத்து என்ன வேண்டும் - வேலை, பயிற்சிப் பணி, பயிற்சி, அல்லது சொந்தத் தொழில்?",
            "te": "తర్వాత మీకు ఏమి కావాలి - ఉద్యోగం, పని చేస్తూ నేర్చుకోవడం, శిక్షణ, లేదా సొంత పని?",
            "bn": "এরপর আপনি কী চান - চাকরি, কাজ করে শেখা, প্রশিক্ষণ, না নিজের কাজ?",
        },
        examples={
            "en": "“I want to start my own business.”",
            "hi": "“मैं अपना काम शुरू करना चाहता हूँ।”",
            "kn": "“ನನಗೆ ನನ್ನದೇ ವ್ಯಾಪಾರ ಶುರು ಮಾಡಬೇಕು.”",
        },
    ),
    SlotDefinition(
        name="mobility",
        priority=60,
        required=True,
        input_type="choice",
        options=MOBILITY_OPTIONS,
        questions={
            "en": "Are you comfortable travelling far for work or training?",
            "hi": "क्या आप काम या प्रशिक्षण के लिए दूर जाने में सहज हैं?",
            "kn": "ಕೆಲಸ ಅಥವಾ ತರಬೇತಿಗಾಗಿ ದೂರ ಪ್ರಯಾಣಿಸಲು ನಿಮಗೆ ಅನುಕೂಲವಿದೆಯೇ?",
            "mr": "काम किंवा प्रशिक्षणासाठी लांब प्रवास करणे तुम्हाला जमेल का?",
            "ta": "வேலை அல்லது பயிற்சிக்காக தூரம் பயணிக்க உங்களுக்கு வசதியா?",
            "te": "పని లేదా శిక్షణ కోసం దూరం ప్రయాణించడం మీకు వీలవుతుందా?",
            "bn": "কাজ বা প্রশিক্ষণের জন্য দূরে যাতায়াত করতে আপনার সুবিধা হবে?",
        },
        help_text={
            "en": "We will not suggest anything beyond this distance.",
            "hi": "हम इससे दूर का कुछ नहीं सुझाएँगे।",
            "kn": "ಈ ದೂರಕ್ಕಿಂತ ಹೆಚ್ಚಿನದನ್ನು ನಾವು ಸೂಚಿಸುವುದಿಲ್ಲ.",
        },
        examples={
            "en": "“I can only work near my village.”",
            "hi": "“मैं गाँव के पास ही काम कर सकता हूँ।”",
            "kn": "“ನಾನು ನನ್ನ ಊರಿನ ಹತ್ತಿರ ಮಾತ್ರ ಕೆಲಸ ಮಾಡಬಲ್ಲೆ.”",
        },
    ),
    SlotDefinition(
        name="location",
        priority=70,
        required=True,
        input_type="location",
        questions={
            "en": "Where are you? You can share your location or type your village or PIN code.",
            "hi": "आप कहाँ हैं? आप अपनी लोकेशन साझा कर सकते हैं या गाँव/पिन कोड लिख सकते हैं।",
            "kn": "ನೀವು ಎಲ್ಲಿದ್ದೀರಿ? ನಿಮ್ಮ ಲೊಕೇಶನ್ ಹಂಚಿಕೊಳ್ಳಬಹುದು ಅಥವಾ ಊರು/ಪಿನ್ ಕೋಡ್ ಟೈಪ್ ಮಾಡಬಹುದು.",
            "mr": "तुम्ही कुठे आहात? लोकेशन शेअर करा किंवा गाव/पिन कोड लिहा.",
            "ta": "நீங்கள் எங்கே இருக்கிறீர்கள்? இருப்பிடத்தைப் பகிரலாம் அல்லது ஊர்/பின் கோடு தட்டச்சு செய்யலாம்.",
            "te": "మీరు ఎక్కడ ఉన్నారు? లొకేషన్ షేర్ చేయండి లేదా ఊరు/పిన్ కోడ్ టైప్ చేయండి.",
            "bn": "আপনি কোথায় আছেন? অবস্থান শেয়ার করুন বা গ্রাম/পিন কোড লিখুন।",
        },
        examples={"en": "your village name or 6-digit PIN code, e.g. “422003”."},
    ),
    SlotDefinition(
        name="interests",
        priority=80,
        required=False,
        input_type="free_text",
        proactive=False,
        questions={
            "en": "Is there any kind of work you especially like doing?",
            "hi": "क्या कोई ऐसा काम है जो आपको ख़ास पसंद है?",
            "kn": "ನಿಮಗೆ ವಿಶೇಷವಾಗಿ ಇಷ್ಟವಾದ ಯಾವುದಾದರೂ ಕೆಲಸ ಇದೆಯೇ?",
            "mr": "तुम्हाला विशेष आवडणारे काही काम आहे का?",
            "ta": "உங்களுக்கு விசேஷமாகப் பிடித்த வேலை ஏதேனும் உண்டா?",
            "te": "మీకు ప్రత్యేకంగా ఇష్టమైన పని ఏదైనా ఉందా?",
            "bn": "কোনো কাজ কি আপনার বিশেষ ভালো লাগে?",
        },
    ),
]

SLOTS_BY_NAME: dict[str, SlotDefinition] = {slot.name: slot for slot in SLOT_DEFINITIONS}

REQUIRED_SLOTS: list[str] = [s.name for s in SLOT_DEFINITIONS if s.required]


def ordered_slots() -> list[SlotDefinition]:
    return sorted(SLOT_DEFINITIONS, key=lambda s: s.priority)


def slot_catalogue(language: str = "en") -> list[dict]:
    """Serialised slot configuration, served to the client."""
    return [
        {
            "name": slot.name,
            "priority": slot.priority,
            "required": slot.required,
            "input_type": slot.input_type,
            "question": slot.question_for(language),
            "help": slot.help_for(language),
            "depends_on": slot.depends_on,
            "options": [
                {"value": o.value, "label": o.label_for(language), "icon": o.icon}
                for o in slot.options
            ],
        }
        for slot in ordered_slots()
    ]
