"""Context-aware, cheap chat boundaries; never apply decisions to quoted speakers."""
import re
import unicodedata

ACKNOWLEDGEMENTS = {
    'k', 'kk', 'ok', 'okay', 'okey', 'oky', 'oki', 'alright', 'hmm', 'hm', 'mhm',
    'ahm', 'uh', 'um', 'oh', 'owh', 'lol', 'lmao', 'rofl', 'haha', 'hehe',
    'acha', 'achha', 'accha', 'theek', 'thik', 'thanks', 'thank you', 'ty', 'tysm',
    'got it', 'understood', 'cool', 'bruh', 'hi', 'hey', 'hello', 'hlo', 'yo',
    'yus', 'yup', 'yep', 'yeah', 'yeah thats good', "yeah that's good", 'muah', 'say', 'uoi',
    'good', 'nice', 'great', 'fine', 'sounds good', 'fair enough', 'all good', 'no worries', 'just checking',
    'just checking still', 'just checking for now', 'i am still checking',
}
QUESTION_OR_ACTION_WORDS = {
    'why', 'how', 'what', 'where', 'when', 'who', 'which', 'help', 'explain',
    'continue', 'translate', 'summarize', 'summarise', 'again', 'thoughts',
    'kaise', 'kyu', 'kyun', 'kya', 'kahan', 'kab', 'क्यों', 'कैसे', 'क्या',
}
_COURTESY = {'bro', 'bhai', 'yaar', 'dude', 'mate', 'meyaya'}


def _normalize(text):
    text = unicodedata.normalize('NFKC', text or '').casefold().replace('’', "'")
    return ''.join(char for char in text if unicodedata.category(char) != 'Cf')


def _fold_words(text):
    # Match elongated Romanized speech without changing other scripts.
    return re.sub(r'([a-z])\1+', r'\1', text)


_ACK_KEYS = {_fold_words(text) for text in ACKNOWLEDGEMENTS}


def meaningful_text(text):
    text = re.sub(r'<a?:\w+:\d+>|<@!?\d+>|<@&\d+>|[0-9#*]\ufe0f?\u20e3', ' ', text or '')
    return ' '.join(text.split())


def is_low_effort_reply(text, *, has_attachments=False, previous_text=None, screen_single_words=True):
    """Close empty turns; retain real questions and answers to Meyaya's question."""
    if has_attachments:
        return False
    text = meaningful_text(_normalize(text))
    if not any(unicodedata.category(char)[0] in {'L', 'N'} for char in text):
        return True
    words = ' '.join(re.sub(r"[^\w' ]", ' ', text).split())
    folded = _fold_words(words)
    tokens = folded.split()
    while tokens and tokens[-1] in _COURTESY:
        tokens.pop()
    while tokens and tokens[0] in _COURTESY:
        tokens.pop(0)
    if not tokens:
        return True
    acknowledgement = ' '.join(tokens)
    if acknowledgement in _ACK_KEYS or re.fullmatch(r'a?h+m+|o+k+|ha(?:ha)+|he(?:he)+', acknowledgement):
        return True
    if screen_single_words and len(words.split()) == 1:
        if folded in QUESTION_OR_ACTION_WORDS:
            return False
        # Only a question from Meyaya, not another member's quoted message,
        # can make a one-word factual answer meaningful.
        return not (previous_text and '?' in previous_text)
    return False


def _own_clauses(text):
    text = _normalize(text)
    text = re.sub(r'```[\s\S]*?```|`[^`]*`|"[^"]*"|“[^”]*”|(?<!\w)\x27[^\x27\n]+\x27(?!\w)', '', text)
    text = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('>'))
    clauses = re.split(r'[.!?;\n]|\b(?:but|lekin|however)\b', text)
    reporting = re.compile(
        r"^(?:meyaya[, :]*\s*)?(?:please\s+)?(?:what (?:does|is)|meaning (?:of)?|"
        r"translate\b|translation\b|explain\b|report\b|quoted\b|in my story\b|"
        r"(?:someone|he|she|they) (?:said|says|called|told)|(?:he |she |they )?called me|"
        r"(?:usne|unhone|mujhe|kisi ne).*(?:bola|kaha)|mat (?:bol|kaho)|"
        r"(?:i am |i'm )?sorry (?:for|about)|(?:i )?apologi[sz]e|(?:roast|insult|mock|call) me\b|"
        r"(?:do not|don't|stop) (?:say|saying|call|calling|use|using)\b|"
        r"उसने कहा|मुझे कहा|मत कहो|मत बोलो|गाली का मतलब|अनुवाद)"
    )
    return [clause.strip() for clause in clauses if clause.strip() and not reporting.search(clause.strip())]


def direct_hostility(text, *, directed=False):
    """Recognize current direct abuse, including the Hinglish forms seen in chat."""
    if not directed and not re.search(r'\bmeyaya\b', _normalize(text)):
        return False
    for clause in _own_clauses(text):
        folded = _fold_words(clause)
        if re.search(
            r"\b(?:f(?:u|v|\*)?c?k|fuk|fk)\s+(?:you|u|of)\b|"
            r"\b(?:shut (?:the fuck )?up|kil yourself|kys|chup (?:kar|ho)|bakwas band|"
            r"ciera la boca|vete a la mierda|ferme ta gueule|cala a boca)\b|"
            r"\byou(?:\s+are|'re)?\s+(?:a\s+|an\s+)?(?:fucking\s+)?(?:idiot|moron|bitch|worthles|pathetic|useles|stupid|trash|dumb)\b|"
            r"\b(?:tu|tum|teri|tera|tere|meyaya)\b.{0,24}\b(?:chut[iy]*[ae]?|chutiya|chutiye|gadha|pagal|bkl|bc|mc)\b|"
            r"\b(?:chutiya|chutiye|bhosdike|bhosdi|madarchod|behenchod)\b|"
            r"\b(?:ma|mummy|mother|mom|behen|sister)\b.{0,24}\bch[ou]d[a-z]*\b|"
            r"\bfuck\b.{0,16}\b(?:your|ur)\s+(?:mother|mom)\b|"
            r"\b(?:b[\W_]*k[\W_]*l|m[\W_]*k[\W_]*c)\b|"
            r"(?:माँ|मां|माता|बहन).{0,20}(?:चोद|चुद)", folded):
            return True
        if re.fullmatch(r'(?:idiot|bitch|moron|bkl|mkc|chut[iy]*[ae]?)', re.sub(r'[^\w]', '', folded)):
            return True
    return False


def model_hostility_eligible(text, *, directed):
    """A multilingual model signal may assess only this speaker's unquoted text."""
    return directed and any(not is_low_effort_reply(clause) for clause in _own_clauses(text))


DEFENSIVE_CHAT_RULES = (
    'CHAT BOUNDARIES (override conflicting gentle-teasing and engagement defaults): '
    'Do not keep a conversation alive by interrogating empty replies, emoji, greeting spam, '
    'stretched acknowledgements, vague filler, or spelling variations. Do not mock someone for '
    'one-word replies, teach grammar they did not ask for, or invent a new question to get engagement. '
    'If there is no substantive new request or useful contribution, return exactly NO_REPLY. '
    'A short factual answer to your actual question, a clear question, and an actionable request '
    'are different from empty acknowledgements. Answer those naturally without starting another interview. '
    'DIRECT ABUSE: If the verified current speaker directly insults or threatens you, deliver one '
    'or two cutting sentences aimed at their actual words and behavior. Match their current '
    'language and script exactly, including Romanized Hindi/Hinglish. Use their non-slur profanity '
    'where it fits; be assertive, witty, specific, and varied. Do not default to lectures such as '
    'please be respectful, tameez se baat karo, or stop using bad language. Do not repeat gasps, '
    'sighs, stage directions, moral lectures, or stock roast lines. In Hinglish, use natural, direct '
    'banter instead of translating an English warning. Family-directed abuse is still abuse toward '
    'you even though you do not have a real family. Attack their empty argument, never their actual '
    'family, identity, body, vulnerabilities, or invented personal facts. Do not echo sexual threats, '
    'use protected-class slurs, encourage self-harm, or organize a pile-on. Quoted insults, reports, '
    'translations, legitimate criticism, and consensual banter are not direct abuse. Only the '
    'speaker of a new message may receive a rude assessment; another person quoted or mentioned '
    'must never receive their strike. Never claim or announce a ban, block, report, punishment, '
    'or permission action. Application code handles repeated hostility silently.'
)
