"""Friendly replies to greetings and thanks, so "hi" gets an introduction instead of a document search.

Only short messages that are *entirely* small talk are answered here. Anything that looks like a real question
(a fault, a procedure, a machine) goes to the document search as usual.
"""
import re

INTRO = (
    "Hi! I'm ForgeMind AI, your industrial maintenance assistant. What can I help you with?\n\n"
    "You can ask me about machine faults and how to fix them, maintenance procedures, safety steps, "
    "or anything written in the manuals and SOPs that have been uploaded."
)
ABOUT = (
    "I'm ForgeMind AI. I answer questions about your machines using the manuals, SOPs and maintenance records "
    "in this system, and I show which document and page each answer comes from. "
    "Try asking: \"What causes low oil pressure on the compressor?\""
)
FINE = "I'm doing well, thank you! What can I help you with today?"
WELCOME = "You're welcome! Ask me anything else about your machines or procedures."
BYE = "Goodbye! Come back any time you need help with your equipment."

_GREETING = r"(hi+|hai+|hello+|hey+|heya|hiya|yo|hola|namaste|namaskar|vanakkam|good\s+(morning|afternoon|evening|day)|greetings)"
_FILLER = r"(there|team|all|everyone|forgemind|forgemind\s+ai|assistant|bot|ai|buddy|friend|sir|madam)"
_RULES = [
    (re.compile(rf"{_GREETING}(\s+{_FILLER})?"), INTRO),
    (re.compile(r"(how\s+are\s+(you|u)|how\s+r\s+u|how'?s\s+it\s+going|what'?s\s+up|sup)"), FINE),
    (re.compile(r"(who\s+are\s+(you|u)|what\s+are\s+(you|u)|what\s+is\s+forgemind(\s+ai)?|what\s+can\s+(you|u)\s+do|"
                r"what\s+do\s+(you|u)\s+do|help|help\s+me|how\s+can\s+(you|u)\s+help(\s+me)?|introduce\s+yourself)"), ABOUT),
    (re.compile(r"(thanks?|thank\s+(you|u)|thx|ty|many\s+thanks|thanks\s+a\s+lot|ok\s+thanks?)"), WELCOME),
    (re.compile(r"(bye|goodbye|see\s+(you|ya)|good\s+night)"), BYE),
]


def reply(question: str) -> str | None:
    """The canned reply when the whole message is small talk, otherwise None."""
    text = re.sub(r"[^a-z' ]+", " ", question.lower())
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text.split()) > 6:
        return None
    for pattern, answer in _RULES:
        if pattern.fullmatch(text):
            return answer
    return None