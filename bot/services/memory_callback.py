"""Conservative callbacks from existing, scoped memory reads. No extra model calls."""
from hashlib import blake2b
import json
import re
import time
import unicodedata

PREFIX = "NATURAL_CALLBACK "
MEMBER_COOLDOWN = 3 * 3600
FACT_COOLDOWN = 7 * 86400
CLAIM_SECONDS = 120
FACT = re.compile(r"^\[(preference|hobby):self:([^;]+); confidence=([0-9.]+)\] (.+)$")
STOP = frozenset("i me my you your like likes love loves enjoy enjoys favorite favourite really very also have want something about what this that with please today usually mujhe mera meri pasand hai hain aur the and for".split())
SENSITIVE = re.compile(r"\b(?:health|medical|diagnosis|cancer|depression|suicide|trauma|religion|politic|sexual|password|address|salary|debt|income)\w*\b", re.I)
BOUNDARY = re.compile(r"\b(?:forget|delete|remove|stop remembering|stop bringing|don't remember|do not remember|no longer|don't like|do not like|don't play|do not play|not anymore|pasand nahi)\b", re.I)
TOPICS = (
    frozenset("music guitar piano singing gaana gane sangeet संगीत गाना गिटार पियानो".split()),
    frozenset("anime manga watching watch dekhu dekhna".split()),
    frozenset("gaming games game videogames khelna khelu".split()),
    frozenset("reading books book novels novel padhna".split()),
    frozenset("cooking baking food cook bake coffee chai खाना चाय".split()),
    frozenset("drawing painting sketch art sketches कला".split()),
)


def words(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = ''.join(c if c.isalnum() or unicodedata.category(c).startswith('M') else ' ' for c in normalized)
    return {word for word in normalized.split() if len(word) >= 3 and word not in STOP}


def candidates(lines, current_text):
    if BOUNDARY.search(current_text) or any(line.startswith("UNFINISHED_TOPIC ") for line in lines):
        return []
    current = words(current_text)
    ranked = []
    for line in lines:
        match = FACT.fullmatch(line)
        if not match or float(match[3]) < 0.8 or len(match[4]) > 200 or SENSITIVE.search(line):
            continue
        fact = words(match[2] + ' ' + match[4])
        overlap = len(current & fact)
        shared_topic = any(current & topic and fact & topic for topic in TOPICS)
        if overlap or shared_topic:
            ranked.append((overlap, line))
    return [line for _, line in sorted(ranked, key=lambda pair: -pair[0])]


class MemoryCallbackGate:
    def __init__(self, redis=None, clock=time.monotonic):
        self.redis, self.clock = redis, clock
        self.recent = {}

    def _remember(self, key, ttl):
        now = self.clock()
        # Keep only suppression timestamps/hashes, never personal fact text.
        self.recent = {k: expires for k, expires in self.recent.items() if expires > now}
        if len(self.recent) >= 2048 and key not in self.recent:
            # Fail closed rather than evicting an unexpired suppression.
            return False
        self.recent[key] = now + ttl
        return True

    async def choose(self, lines, current_text, guild_id, user_id):
        member = f"meyaya:callback:{guild_id}:{user_id}"
        if self.recent.get(member, 0) > self.clock():
            return None
        for fact in candidates(lines, current_text):
            match = FACT.fullmatch(fact)
            identity = '|'.join((match[1], match[2], ' '.join(match[4].casefold().split())))
            digest = blake2b(identity.encode('utf-8'), digest_size=16).hexdigest()
            key = member + ':' + digest
            if self.recent.get(key, 0) > self.clock():
                continue
            try:
                if self.redis is not None:
                    if not await self.redis.set(member, 'pending', nx=True, ex=CLAIM_SECONDS):
                        return None
                    if not await self.redis.set(key, 'pending', nx=True, ex=CLAIM_SECONDS):
                        return None
            except Exception:
                return None
            if not self._remember(member, CLAIM_SECONDS) or not self._remember(key, CLAIM_SECONDS):
                return None
            return PREFIX + json.dumps({'member': member, 'key': key, 'fact': fact}, ensure_ascii=False)
        return None

    async def delivered(self, lines):
        for line in lines:
            if not line.startswith(PREFIX):
                continue
            data = json.loads(line[len(PREFIX):])
            for key, ttl in ((data['member'], MEMBER_COOLDOWN), (data['key'], FACT_COOLDOWN)):
                self._remember(key, ttl)
                if self.redis is not None:
                    try:
                        await self.redis.set(key, '1', ex=ttl)
                    except Exception:
                        pass  # Local suppression remains; chat delivery already succeeded.
