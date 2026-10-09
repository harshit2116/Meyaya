"""Canonical Memory World cinematics, reveal gates and permanent worldlines.

Origin/Erasure are natural processes. Their channelers are people, not gods
embodying those processes. Reset unfinished cinematics when changing story versions.
"""
from dataclasses import dataclass

CYCLE = 33_550_336
PREVIOUS_CYCLES = CYCLE - 1
STORY_VERSION = 3
ORIGIN_COLOR = 0xE7A9CB
ENDING_TITLES = {"meyaya": "THE WORLD THAT CONTINUES", "veyra": "THE LAST SILENCE"}


@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    dialogue: str
    asset: str
    floor: int = 0
    route: str = "shared"
    reveal_flags: tuple[str, ...] = ()
    anchor: int | None = None
    encounter: int | None = None
    boss: str | None = None
    ending_route: str | None = None


def scene(key, title, text, asset, *, floor=0, flags=(), anchor=None, route="shared"):
    return Scene(key, title, text, asset, floor, route, flags, anchor,
                 ending_route=route if route in ENDING_TITLES else None)


# Shown only after the Floor 10 disguise reveal. Existing art is reused.
BACKSTORY = (
    scene("universe", "BEFORE THEIR NAMES", "Long before Meyaya or Veyra, the real universe lived. Stars formed, worlds ended, and their remnants became beginnings elsewhere. Origin and Erasure were processes of reality. Neither needed a face or a name.", "cinematic/real-universe", floor=10),
    scene("origin", "ORIGIN", "Matter gathered. A star ignited. On a young world, something living reached toward light. Origin was the possibility of formation, present billions of years before anyone learned to channel it.", "cinematic/origin-force", floor=10),
    scene("erasure", "ERASURE", "Elsewhere, structures unraveled and lives ended. Erasure belonged to the same reality. An ending could make room for a beginning, but nothing guaranteed that those who suffered would see what followed.", "cinematic/erasure-force", floor=10),
    scene("beings", "TWO WHO COULD REACH IT", "After billions of years, two extraordinary beings emerged. Meyaya could channel Origin; Veyra could channel Erasure. They had bodies, limits, and convictions. The forces were older than either of them.", "cinematic/emergence", floor=10),
    scene("together", "WHAT THEY WATCHED", "They watched cities rise and people grow old. Meyaya remembered the first flowers after a fire. Veyra remembered those who had burned. For a long time they stood together, looking at the same universe and carrying different parts of it away.", "cinematic/before-conflict", floor=10),
    scene("conflict", "ANOTHER CHANCE", "Meyaya: ‘Something ending does not make it meaningless. Existence does not need to be perfect. It only needs another chance.’\n\nVeyra: ‘Another chance for whom? The next life does not spare the one that suffered.’", "cinematic/philosophical-conflict", floor=10),
    scene("decision", "NO MORE BEGINNINGS", "Veyra resolved to stop the process itself. ‘There should be no more beginning. There should be no more ending. There should simply be silence.’ She did not ask the living whether they wished to lose their future.", "cinematic/veyra-decision", floor=10),
    scene("confrontation", "THE FIRST REFUSAL", "Meyaya stood in her path. She could not accept an end imposed on every life yet to exist. Their disagreement became a struggle between two people drawing upon powers far greater than themselves.", "cinematic/first-confrontation", floor=10),
    scene("containment", "WHAT COULD NOT BE KILLED", "Meyaya stopped Veyra before she could end the universe. Destroying her body would release the Erasure already gathered within it. Containment was the only answer Meyaya could find that did not risk the catastrophe she was trying to prevent.", "cinematic/containment", floor=10),
    scene("construction", "THE MEMORY WORLD", "Meyaya made a sealed artificial reality outside the normal universe. She built it from her memories: a sunset kingdom, a drowned city, voices she could not bear to lose. It was a construct, not another natural universe.", "cinematic/memory-construction", floor=10, flags=("memory_world",)),
    scene("prison", "AT ITS CENTER", "She bound Veyra at the center and distributed the prison's restraints through ten anchors. The seal restricted Veyra's access to her own accumulated power and to the Erasure beyond it. Outside, the real universe continued untouched.", "cinematic/imprisonment", floor=10),
    scene("keeper", "THE KEEPER", "Meyaya stayed to maintain the containment. Leaving would free Veyra. She had made a monument to what she loved, a prison for someone she could not safely destroy, and a place she could no longer leave.", "cinematic/keeper", floor=10),
    scene("failsafe", "WHEN MEMORY FAILS", "The construct could degrade. Meyaya gave it a failsafe: at catastrophic failure, reconstruct the regions and restore the anchors from stored memories. This automatic reconstruction belonged to the Memory World alone. Outside it, time and life went on.", "cinematic/reconstruction", floor=10),
    scene("cycle", f"CYCLE {CYCLE:,}", "Reconstruction begins. Towers assemble from light. Water finds the shapes of streets. The last grain of an extinguished sunset returns to its place. Something remains between the restored pieces.", "cinematic/cycle-begin", floor=10),
)

OPENING = (
    scene("consciousness", "THE AWAKENING", "You wake alone in a field beneath an unfamiliar sky. Silver-white hair falls across your hands. A puddle reflects a young human woman whose face you cannot place. Far away, immense golden towers rise beneath a crimson sun.\n\nYou cannot remember your home, your family, or how you arrived. Even your own name will not come. A faint grief catches in your chest, familiar without a face. You wait for it to become a memory. It does not. Perhaps someone among those towers can help.", "cinematic/player-field-awakening"),
    scene("identity", "IDENTITY: NOT FOUND", "A narrow light passes over your face. Letters gather in the air.\n\nIDENTITY: NOT FOUND\nNO MATCH FOUND\nRECONSTRUCTION RECORD: ABSENT\n\n‘What record?’ you ask. The light searches again, then fades without answering. Your hand is still warm. You are still breathing. You rise and follow the road toward the towers.", "cinematic/player-registration"),
    scene("settlement", "WAITING FOR MORNING", "The settlement is called Solenne. Its arches lean toward the unmoving crimson sun. Dead flowers line the road; shutters soften a light that never changes. A woman turns a calendar page bearing the same date as the last.\n\n‘Does morning have a sound?’ a child asks you. You look up, hoping the sky will give you an answer. It does not.", "solenne/world"),
    scene("inhabitants", "WHAT THEY KEEP READY", "A gardener tends flowers that have never opened. Beside his sleeping daughter he sets a fresh cup. ‘For when she wakes to morning,’ he says. At the next corner, a lamplighter polishes an unused lamp. His grandmother taught him the route in case night returned.\n\nYou help him wind a new wick. He gives you the spare. You have no memory of home, but you understand the care with which he keeps this one ready.", "solenne/world"),
    scene("companion", "THE WOMAN AT THE THRESHOLD", "At a damaged boundary, a pink-haired woman appears in a wavering projection. She reaches toward you; her hand stops at the light. You touch its edge, and a channel brightens beneath your fingers. Her eyes widen.\n\n‘It answered you? Try again-only if you want to.’ The channel opens for your hand. Hers still cannot pass.\n\n‘I can speak through these cracks, but I cannot cross them myself.’ She studies your hand, then looks along the road beyond it. ‘I hadn't expected to meet anyone it would let through.’", "cinematic/player-boundary-meeting"),
    scene("mission", "A LEAD CALLED THE ORIGIN GATE", "‘I'm Meyaya,’ she says. ‘Ten worlds are suffering. Fragments scattered through them are connected to an ancient structure called the Origin Gate. Together they should let us reach it-and end what keeps these places trapped. I need someone who can reach the places I cannot.’\n\nYou tell her about the light that found no record of you. ‘Could this Gate tell me who I am?’\n\n‘Perhaps. I cannot promise that. But whatever let you touch this boundary may matter there too. It is the best lead I can offer.’\n\nYou remember the child waiting for a morning she has never seen.", "cinematic/player-boundary-meeting"),
    scene("departure", "THE ROAD YOU CHOOSE", "‘I don't know whether I can trust you,’ you say.\n\n‘I haven't given you much reason yet,’ Meyaya answers.\n\nYou look back at the lamps and the unopened flowers. ‘I want to know why there's no record of me. And if there's a chance that child can see morning, I want to find it.’ You close your hand around the spare wick. ‘I'll try your road. I'll ask questions. If what we find doesn't match your promise, I decide what happens next.’\n\nMeyaya nods. You take the first step through the boundary. Her projection follows along its broken edge, unable to take that step for you.", "cinematic/player-boundary-meeting"),
)

CYCLE_RECORDS = "\n".join([f"CYCLE {n:,} - RESET" for n in range(CYCLE - 5, CYCLE)] + [f"CYCLE {CYCLE:,} - ACTIVE"])
NULLIS_REVELATION = (
    scene("records", "THE RECORD VAULT", CYCLE_RECORDS + "\n\nMEYAYA - KEEPER\nVEYRA - BOUND\nRECONSTRUCTION - AUTOMATIC FAILSAFE\nANCHORS - RESTORED AFTER EACH FAILURE\n\nTravelers fill the intervening records. No completed attempt opened a way out.", "cinematic/cycle-records", floor=9, flags=("cycles",)),
    scene("discovery", "SHE STOPS READING", "The woman you know as Meyaya goes still. Her finger moves back to the first number, then to the last. ‘No...’\n\nShe searches a previous traveler's record as though it might tell her something different. ‘I would remember. I would remember this.’\n\nYou have never heard her voice sound small before.", "cinematic/cycle-discovery", floor=9),
    scene("breakdown", "WHAT SHE CANNOT REMEMBER", f"‘{PREVIOUS_CYCLES:,} times?’ Her hand will not stay steady. ‘How many times have you done this to me?’\n\nShe presses her palms against her eyes. There is no memory to meet the number-only the terror of discovering that her life has been taken from her again and again. When you reach for her, she flinches, then stays.", "cinematic/cycle-breakdown", floor=9, flags=("companion_fear",)),
    scene("keeper-record", "TWO PRISONERS", "The keeper's log never records a departure. The same presence remained through every reconstruction. ‘You stayed?’ your companion whispers. Rage gives way to something she cannot name.\n\nShe folds the page instead of destroying it. You notice she has stopped calling the vault mistaken.", "cinematic/forgotten-cycles", floor=9),
    scene("anomaly-record", "AN ENTRY THAT DID NOT EXIST", "The current cycle includes an exception: UNREGISTERED CONSCIOUSNESS - NO MATCH FOUND. No earlier traveler has the same reading.\n\nBeside it, a damaged diagram joins the fragments to a central boundary. You cannot tell what runs through its channels. Your companion searches its missing labels with you. ‘We need to reach the center,’ she says, and this time it sounds like a question she needs answered too.", "cinematic/traveler-traces", floor=9, flags=("anomaly_hint",)),
)

CORE = (
    scene("core", "THE MEMORY CORE", "No sky remains above you. The path ends inside an immense mechanism whose surfaces carry pieces of every place you crossed. Nine fragments orbit an empty socket. A tenth anchor component waits beneath your hand.", "cinematic/memory-core", floor=10),
    scene("convergence", "TEN POINTS", "The fragments move into a pattern. Solenne's light enters one channel; Nymora's voices enter another. They answer each other as parts of a single structure. Your companion cannot reach across its last boundary. You can.", "cinematic/anchors-converge", floor=10),
    scene("placement", "THE LAST COMPONENT", "You set the final component in place. A doorway rises around it, magnificent and familiar. For one breath it looks exactly like the promise that brought you here.", "cinematic/final-anchor", floor=10, anchor=10),
    scene("gate", "THE ORIGIN GATE", "There is no distance through the doorway. Its far side is the same room. The frame flickers, exposing an instruction: EXIT INTERPRETATION - INCOMPLETE. A name was given to something nobody had successfully understood.", "cinematic/false-gate", floor=10),
    scene("collapse", "THERE WAS NEVER AN ORIGIN GATE", "The doorway collapses. Behind its frame, ten restraints run inward toward a prison. The fragments were its seal anchors. There was never an Origin Gate.\n\nYou turn to the woman who promised you a way to save Solenne. ‘What have I been opening?’", "cinematic/gate-collapse", floor=10, flags=("false_gate",)),
    scene("identity-reveal", "VEYRA", "Pink drains from your companion's hair. The imprint falls away. The woman beneath it is Veyra-the same presence that has walked beside you, using Meyaya's identity as a mask.\n\n‘I needed a hand the anchors would not refuse. I knew I was imprisoned. I did not know how many times.’ There is no second impostor standing behind her.", "special/veyra-reveal", floor=10, flags=("veyra_identity",)),
    scene("real-meyaya", "THE REAL MEYAYA", f"At the center stands the actual keeper. Pink light binds her to every damaged region. She has maintained this prison through {CYCLE:,} cycles. She looks from you to the woman beside you. ‘You used my imprint.’", "special/meyaya-imprisoned", floor=10, flags=("real_meyaya",)),
    scene("bound-veyra", "BEHIND THE KEEPER", "Beyond the keeper's ring, you see Veyra's bound body move with her projection. The two images answer the same gesture. The seal carries Meyaya's identity through every boundary. Through its cracks, Veyra learned to resonate along those same paths. She could borrow permission to project her voice and image. She could not cross the prison boundaries or take an anchor.", "cinematic/imprisoned-veyra", floor=10),
    scene("testimony", "WHAT THE RECORDS PROVED", f"Veyra puts the folded record between them. ‘{PREVIOUS_CYCLES:,} completed cycles. I remember none of them.’\n\nMeyaya: ‘The reconstruction strips away what the current world cannot carry. I could delay failures. I could not make a degrading memory last forever.’\n\nVeyra: ‘And neither of us was allowed to leave.’\n\nMeyaya touches the record. Around you, Solenne’s light and Nymora’s voices give way to older memories. ‘You deserve to see what brought us here.’", "cinematic/core-records", floor=10, flags=("failsafe",)),
    *BACKSTORY,
    scene("unbound", "AN UNBOUND SOUL", "Meyaya studies your registration failure. Millions of reconstructions left tiny residues: grief, unfinished memories, emotions, soul fragments, residual consciousness, traces of earlier travelers, inconsistencies the failsafe left behind. They accumulated until something new became aware.\n\nYou are not a returned traveler, a hidden god, or either woman's equal in power. You are an emergent soul the reconstruction cannot completely erase. There was no record because you were a new person, not a restored entry. The anchors could not refuse someone their rules did not register. Familiar gestures belonged to your sources; the person making them now is you.", "cinematic/unbound-reveal", floor=10, flags=("unbound_soul",)),
    scene("keeper-explains", "THE COST OF PRESERVATION", "Meyaya: ‘Destroying Veyra would have released what she had gathered. I made a separate place to contain her, from the memories I could preserve. I stayed because the seal needed a keeper.’\n\nShe looks at the regions suspended around her. ‘I remembered them so carefully that I stopped asking what living inside those memories would cost.’", "cinematic/meyaya-explains", floor=10),
    scene("outside", "THE UNIVERSE OUTSIDE", "Beyond the construct, the real universe is alive. Stars have formed and died while these memories repeated. Its time was never frozen. Its people were never erased by these resets. The Memory World's existence did not halt or damage it.\n\nWhat happens when this containment opens is a different question.", "cinematic/real-universe", floor=10, flags=("real_universe",)),
    scene("anchors", "WHAT YOUR HANDS OPENED", "Each anchor kept a portion of Veyra's power beyond her reach. Each one you broke returned access to what was already hers. The fragments created nothing. You thought each fragment was a step toward morning for Solenne. You have dismantled the prison one restraint at a time. The wick in your hand has never been lit.", "cinematic/anchor-seal", floor=10, flags=("anchors",)),
    scene("break", "THE SEAL BREAKS", "The last restraint opens. Across the Core, the ten anchors go dark. This is the end of a containment system, not the creation of a new force. Veyra reaches for the power that was always hers.", "cinematic/seal-break", floor=10, flags=("seal_broken",)),
    scene("release", "UNBOUND ERASURE", "Her imprisoned presence and borrowed projection become one. Erasure flows through channels the seal kept closed. Meyaya no longer has to hold the mechanism together; Veyra no longer has to reach through its cracks.", "cinematic/veyra-release", floor=10),
    scene("power", "WHAT THE PRISON WITHHELD", "For the first time in this journey, Veyra can draw freely upon Erasure beyond the artificial world. Her restored access changes the scale of the danger. You have not become stronger than her by opening the lock.", "cinematic/veyra-power", floor=10, flags=("full_erasure",)),
    scene("passage", "OUTSIDE MEMORY", "The broken boundary opens onto the real universe. Meyaya and Veyra pass beyond the structure that held them. You follow as the witness to what happened inside it. The worlds behind you will not secretly reconstruct after this.", "cinematic/real-transition", floor=10),
    scene("judge", "THE WITNESS", "You have seen lives preserved beyond endurance and endings that took more than suffering away. Neither woman can claim you have seen only her side.\n\nYou cannot fight this battle for them. You can decide whose purpose you stand behind. Your first oath does not make that decision for you.", "cinematic/witness", floor=10, flags=("witness",)),
)

CHOICE = scene("choice", "CONTINUATION OR FINALITY", "🌸 **STAND WITH MEYAYA**\nLet the world continue.\n\n⚫ **STAND WITH VEYRA**\nLet the cycle end.\n\nThis records your permanent worldline. It can differ from your awakening alignment. Rebirth will not change it.", "cinematic/final-choice", floor=10)

COSMIC = (
    scene("battlefield", "BEYOND THE MEMORY WORLD", "The real universe stretches around the two women. The player who opened a prison stands far from its former prisoners. Your choice has been heard. What follows belongs to Meyaya and Veyra.", "cinematic/cosmic-battlefield", floor=10),
    scene("origin-strike", "WHAT MEYAYA MAKES", "Meyaya channels Origin into structures that catch the first advance of Erasure. Light becomes matter. Broken paths become bridges. She is using a force that existed before her, giving it direction through the limits of her own body.", "cinematic/meyaya-origin", floor=10),
    scene("erasure-strike", "WHAT VEYRA UNMAKES", "Veyra passes through those structures. Their matter loses cohesion; their light ceases. She can destroy each thing Meyaya makes, but sees new things forming beyond them. Destroying worlds one by one will never end the process that makes more.", "cinematic/veyra-erasure", floor=10),
    scene("collision", "A FUTURE AT EVERY EDGE", "Creation meets destruction across distances you cannot comprehend. Meyaya tries to preserve a future beyond each rupture. Veyra sees another beginning carrying the possibility of another wound. Neither can make the other stop seeing what she sees.", "cinematic/cosmic-collision", floor=10),
    scene("fracture", "THE LIMIT OF A BODY", "As reality begins to fracture, Veyra changes what she is doing. She stops throwing Erasure outward. She draws it inward, gathering the available force through herself. Her body becomes the medium for an ending no ordinary body can survive.", "cinematic/erasure-medium", floor=10),
    scene("unstable", "SHE KNOWS", "Dark fissures cross her skin. Portions of her outline cease before the rest can follow. Meyaya understands.\n\n‘Veyra... you'll tear yourself apart.’\n\n‘I know.’", "cinematic/veyra-unstable", floor=10),
    scene("stop", "THE LAST APPEAL", f"Meyaya reaches for her. ‘You don't have to do this.’\n\nVeyra: ‘You spent {CYCLE:,} cycles trying to save everything. Let me save you from having to do it again.’\n\nShe accepts her own disappearance. The lives beyond her never consented to share it.", "cinematic/last-appeal", floor=10),
    scene("release", "THE FINAL RELEASE", "Veyra releases what her body can no longer contain. There is no fireball, no wreckage expanding through a surviving sky. The conditions that let the old universe continue begin to cease.", "cinematic/final-release", floor=10),
    scene("stars", "THE STARS", "One star disappears. Then there are fewer directions in which light can arrive. No ashes mark where they were. You witness until there is too little light left to see.", "cinematic/stars-vanish", floor=10),
    scene("matter", "THE LAST DISTANCE", "Matter ceases. The space between what remains contracts out of meaning. Time loses the events by which it could be measured. Veyra is gone. Your own awareness ends. No hidden fragment of you escapes the old universe.", "cinematic/spacetime-ends", floor=10),
)

MEYAYA_ENDING = (
    scene("remnant", "THE LAST ORIGIN", "The old universe is gone. The player and Veyra are gone. Meyaya barely remains with the last remnants of Origin. There is no old world waiting intact behind the darkness, and no way to return everyone to their places.", "cinematic/last-origin", floor=10, route="meyaya"),
    scene("decision", "NOT A RESTORATION", "She could spend the last of herself trying to remember every detail. She finally lets that demand go. ‘Something does not become meaningless because it ends.’\n\nWhat she offers is a beginning that will not be a copy of what was lost.", "cinematic/new-decision", floor=10, route="meyaya"),
    scene("point", "A FIRST POINT", "Meyaya channels the remaining Origin. A point forms. It does not contain your memories or the blueprint of the prison. It is the first event of a genuinely new universe.", "cinematic/first-creation", floor=10, route="meyaya"),
    scene("matter", "ROOM TO BECOME", "Space expands. Matter forms. The energy that gives the new universe room to become comes from Meyaya. With every beginning, less of the person who chose it remains.", "cinematic/new-matter", floor=10, route="meyaya"),
    scene("creator", "HER LAST FORM", "For a final moment she is recognizable in the light. Then her outline dissolves into creation. She leaves no surviving mind within it, no hidden goddess, no waiting voice. Her sacrifice is complete.", "cinematic/creator-sacrifice", floor=10, route="meyaya"),
    scene("galaxies", "AFTER HER", "Stars gather into galaxies. Worlds form. Much later, life begins without knowing the name of the woman whose last act made its existence possible. These are new lives, not returned ones.", "cinematic/new-universe", floor=10, route="meyaya"),
    scene("continues", "THE WORLD THAT CONTINUES", "Meyaya is gone. Veyra is gone. You are gone. The old universe is gone.\n\nSomething new has been given the chance to exist.\n\nWORLDLINE: CONTINUATION", "cinematic/world-continues", floor=10, route="meyaya"),
)

VEYRA_ENDING = (
    scene("refusal", "NO NEXT BEGINNING", "Meyaya reaches for a remnant from which another beginning might form. Veyra's final release has reached the processes that would allow it. The attempt fails. Meyaya disappears with the last possibility of creation.", "cinematic/creation-ceases", floor=10, route="veyra"),
    scene("all", "NO ONE BEYOND IT", "There is no consciousness left to experience silence. No space survives as a void realm. No time waits for a future event. Veyra did not spare herself. No player, keeper, prisoner, soul, or secret fragment remains.", "cinematic/absolute-erasure", floor=10, route="veyra"),
    scene("silence", "THE LAST SILENCE", "WORLDLINE: ERASURE\n\nNO WORLD\nNO LIFE\nNO SOUL\nNO ONE REMAINS.", "cinematic/black", floor=10, route="veyra"),
)


def ending_scenes(route):
    return COSMIC + (VEYRA_ENDING if route == "veyra" else MEYAYA_ENDING)


def current_scene(run, profile):
    sequence = run.state.get("sequence", "core")
    if sequence == "opening":
        return OPENING[run.state.get("scene", 0)]
    if sequence == "choice":
        return CHOICE
    if sequence == "ending":
        return ending_scenes(profile.ending_route)[run.state.get("scene", 0)]
    return CORE[run.state.get("scene", 0)]
