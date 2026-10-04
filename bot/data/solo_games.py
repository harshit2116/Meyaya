"""Handwritten adventures, fair mystery evidence, and personality questions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Choice:
    key: str
    label: str
    outcome: str
    cost: int = 1
    item: str = ""
    requires: str = ""
    next_scene: str = ""


@dataclass(frozen=True)
class Scene:
    text: str
    choices: tuple[Choice, ...]


@dataclass(frozen=True)
class Adventure:
    title: str
    intro: str
    scenes: dict[str, Scene]
    special_ending: str


ADVENTURES = (
    Adventure("The midnight mall", "The final shutters close in eight minutes. Reach the staff exit.", {
        "start": Scene("A directory, a service desk and a toy-shop shortcut split the empty concourse.", (
            Choice("map", "Take the floor map", "The map marks a staff passage behind the fountain.", item="floor map", next_scene="passage"),
            Choice("desk", "Visit the service desk", "A guard lends you a radio, but explaining yourself takes a minute.", cost=2, item="radio", next_scene="passage"),
            Choice("toys", "Cut through the toy shop", "You dodge a marching toy army and find the maintenance corridor.", cost=2, next_scene="maintenance"),
        )),
        "passage": Scene("The staff passage forks. A locked tool cabinet stands beside the longer public corridor.", (
            Choice("marked", "Follow your map", "Your marked route saves a detour. A keycard hangs at the maintenance station.", item="keycard", requires="floor map", next_scene="gate"),
            Choice("radio", "Ask the guard by radio", "The guard remotely opens the tool cabinet. You borrow a keycard.", item="keycard", requires="radio", next_scene="gate"),
            Choice("public", "Use the public corridor", "The long corridor gets you to the same security gate without a keycard.", cost=2, next_scene="gate"),
        )),
        "maintenance": Scene("A cleaner is packing up beside a trolley of lost property.", (
            Choice("ask", "Ask for an exit keycard", "The cleaner checks your receipt and lends you a keycard.", cost=2, item="keycard", next_scene="gate"),
            Choice("torch", "Borrow a torch", "You borrow the spare torch and head for the security gate.", item="torch", next_scene="gate"),
            Choice("follow", "Follow the exit signs", "The signs lead you around two closed escalators.", cost=2, next_scene="gate"),
        )),
        "gate": Scene("A security gate blocks the staff corridor. Its reader glows beside an intercom.", (
            Choice("card", "Swipe the keycard", "The gate opens immediately.", requires="keycard", next_scene="dark"),
            Choice("intercom", "Use the intercom", "Security verifies your location and buzzes you through.", cost=2, next_scene="dark"),
            Choice("detour", "Find another entrance", "The gate wraps around the whole corridor. You return to the intercom.", cost=3, next_scene="dark"),
        )),
        "dark": Scene("The last corridor has gone dark. A delivery crate sits in the middle of the floor.", (
            Choice("torch", "Light the way", "Your torch reveals the crate and the staff door beyond it.", requires="torch", next_scene="exit"),
            Choice("lights", "Switch on emergency lights", "The illuminated route takes you safely around the crate.", next_scene="exit"),
            Choice("rush", "Rush toward the exit sign", "You catch the crate with your foot and stop to collect your scattered snacks.", cost=2, next_scene="exit"),
        )),
        "exit": Scene("The staff exit is in sight. A guard is also opening the main doors for a final sweep.", (
            Choice("special", "Use the staff exit", "The keycard clicks. You step into the cool night with your snacks intact.", requires="keycard"),
            Choice("guard", "Leave with the guard", "The guard escorts you out and recommends checking closing times next visit.", cost=2),
        )),
    }, "After-hours insider"),
    Adventure("The runaway snack train", "Your stop has vanished behind you. Reach the next platform in eight minutes.", {
        "start": Scene("A route display flickers beside the conductor's booth and the snack carriage.", (
            Choice("route", "Study the route display", "You copy the correct carriage number and the conductor's access code.", item="access code", next_scene="conductor"),
            Choice("snack", "Enter the snack carriage", "A loose trolley rattles toward you between rows of pudding cups.", next_scene="trolley"),
            Choice("call", "Call for the conductor", "The conductor arrives after finishing a ticket check.", cost=2, next_scene="conductor"),
        )),
        "conductor": Scene("The conductor offers a choice of supplies before returning to the engine.", (
            Choice("pass", "Ask for a service pass", "You receive a pass for the fast platform exit.", item="service pass", next_scene="door"),
            Choice("strap", "Borrow a luggage strap", "The strap could secure the luggage sliding around the next carriage.", item="strap", next_scene="door"),
            Choice("story", "Explain your entire journey", "The conductor is sympathetic, but your dramatic retelling costs time.", cost=2, next_scene="door"),
        )),
        "trolley": Scene("The loose snack trolley blocks the only way forward.", (
            Choice("brake", "Press its marked brake", "The trolley stops. The grateful attendant lends you a service pass.", item="service pass", next_scene="door"),
            Choice("strap", "Secure it with a spare strap", "You anchor the trolley, keep the spare strap, and squeeze past.", cost=2, item="strap", next_scene="door"),
            Choice("surf", "Ride it down the aisle", "The attendant rescues you from a spectacular pudding collision.", cost=3, next_scene="door"),
        )),
        "door": Scene("A locked connecting door separates you from the final carriage.", (
            Choice("code", "Enter the access code", "The code works, and you slip through before the announcement ends.", requires="access code", next_scene="bags"),
            Choice("pass", "Scan the service pass", "The reader accepts the attendant's pass.", requires="service pass", next_scene="bags"),
            Choice("bell", "Ring for assistance", "The conductor walks back to unlock the door.", cost=2, next_scene="bags"),
        )),
        "bags": Scene("A stack of luggage slides across the aisle as the train begins slowing down.", (
            Choice("strap", "Secure the luggage", "Your strap holds the stack clear of the aisle.", requires="strap", next_scene="exit"),
            Choice("rack", "Move bags onto the rack", "You and another passenger put the bags safely out of the way.", cost=2, next_scene="exit"),
            Choice("jump", "Attempt a dramatic leap", "Your coat catches a handle. Untangling it takes longer than moving the bags.", cost=3, next_scene="exit"),
        )),
        "exit": Scene("The train stops. The service door is clear; the public exit has a queue.", (
            Choice("special", "Take the service exit", "You step onto the platform carrying a complimentary pudding.", requires="service pass"),
            Choice("queue", "Join the public exit queue", "You reach the platform just before the departure whistle.", cost=2),
        )),
    }, "Pudding express"),
    Adventure("The moonlight observatory", "An automated roof closes in eight minutes. Get down from the viewing deck.", {
        "start": Scene("A weather desk and an equipment store flank the locked stairwell.", (
            Choice("desk", "Read the weather console", "A maintenance note gives you the stairwell override code.", item="override code", next_scene="desk"),
            Choice("store", "Search the equipment store", "You find a torch and a panel labelled backup power.", item="torch", next_scene="power"),
            Choice("window", "Look for a balcony route", "The balcony ends at a locked safety gate. You return to the desk.", cost=2, next_scene="desk"),
        )),
        "desk": Scene("A caretaker answers the desk intercom. They can send one item through the service lift.", (
            Choice("key", "Request the lift key", "The service lift arrives with a small brass key.", item="lift key", next_scene="stairs"),
            Choice("torch", "Request a torch", "You collect a torch for the unlit maintenance landing.", item="torch", next_scene="stairs"),
            Choice("complain", "Complain about the opening hours", "The caretaker explains the hours while the clock keeps moving.", cost=2, next_scene="stairs"),
        )),
        "power": Scene("The backup panel has a printed instruction card. A service drawer is powered by it.", (
            Choice("manual", "Follow the printed instructions", "Power returns to the service drawer. Inside is the lift key.", item="lift key", next_scene="stairs"),
            Choice("call", "Ask the caretaker for help", "The caretaker walks you through the reset and reads out the override code.", cost=2, item="override code", next_scene="stairs"),
            Choice("switches", "Try every switch", "The dome starts playing its welcome jingle. You wait for the panel to reset.", cost=3, next_scene="stairs"),
        )),
        "stairs": Scene("The stairwell keypad is locked, but the caretaker can also open it remotely.", (
            Choice("code", "Enter the override code", "The lock releases with a reassuring click.", requires="override code", next_scene="landing"),
            Choice("call", "Ask for a remote unlock", "The caretaker finishes securing the dome, then opens the stairwell.", cost=2, next_scene="landing"),
        )),
        "landing": Scene("The maintenance landing is unlit. A glow strip follows the longer wall route.", (
            Choice("torch", "Use your torch", "The beam picks out a clear path to the lift.", requires="torch", next_scene="exit"),
            Choice("strip", "Follow the glow strip", "You follow the wall safely around the stored telescope parts.", cost=2, next_scene="exit"),
            Choice("dash", "Dash across the darkness", "A telescope tripod trips you up. You stop and find the marked route.", cost=3, next_scene="exit"),
        )),
        "exit": Scene("The lift and a final flight of stairs both lead to the front doors.", (
            Choice("special", "Unlock the service lift", "The lift delivers you to the entrance as the dome seals above you.", requires="lift key"),
            Choice("stairs", "Take the final stairs", "You reach the caretaker at the entrance, breathless but safely downstairs.", cost=2),
        )),
    }, "Last light keeper"),
)


@dataclass(frozen=True)
class Case:
    title: str
    intro: str
    evidence: tuple[tuple[str, str], ...]
    explanation: str


# a and b have independent verifiable alibis; c is the remaining suspect.
# Names are reassigned on each run. No single initial clue names the culprit.
CASES = (
    Case("The missing festival trophy", "The trophy disappeared between 20:10 and 20:12. Only three volunteers had access.", (
        ("Examine the display", "The cabinet was opened with a volunteer badge, not forced. All three suspects have valid badges."),
        ("Check the stage recording", "An uncut recording shows {a} presenting onstage from 20:05 to 20:20. The stage is ten minutes from the cabinet."),
        ("Check the kitchen camera", "The kitchen camera shows {b} continuously washing dishes from 20:00 to 20:15. Nobody leaves that room."),
        ("Interview the caretaker", "The caretaker confirms the trophy was present at 20:10 and missing at 20:12. There are no other entrances or badge holders."),
    ), "{a} was onstage and {b} was in the kitchen throughout the theft. Only {c} could reach the cabinet; their badge opened it. The trophy was later recovered from their storage box."),
    Case("The silent karaoke finale", "The microphone vanished between 21:30 and 21:32. Three performers had keys to its case.", (
        ("Inspect the microphone case", "The lock is intact. All three performers have matching keys, so possession of a key alone proves nothing."),
        ("Review the duet video", "{a} appears in a continuous live duet from 21:25 to 21:35, on a stage several corridors away."),
        ("Review the lift footage", "{b} is stuck in a glass lift from 21:28 to 21:40. The footage shows no exit during that interval."),
        ("Ask the sound technician", "The technician checked the microphone at 21:30 and discovered it missing at 21:32. No spare key exists."),
    ), "The duet recording clears {a}; the lift footage clears {b}. Only {c} had both a key and an opportunity. The microphone was found inside their instrument bag."),
    Case("The great pudding switch", "A prize pudding was replaced with a potato between 18:00 and 18:02. Only three contestants could enter the cold room.", (
        ("Inspect the cold room", "The door logs show a valid contestant pass. The display cannot be reached through the serving hatch."),
        ("Watch the cooking broadcast", "{a} appears continuously on a live cooking broadcast from 17:55 to 18:10. The studio is in another building."),
        ("Check the delivery footage", "{b} is visible throughout an unload from 17:58 to 18:05. The loading bay is too far away for a two-minute round trip."),
        ("Question the judge", "The judge saw the real pudding at 18:00 and the potato at 18:02. Only the three named contestants had passes."),
    ), "{a}'s broadcast and {b}'s delivery footage account for the whole window. That leaves {c}, whose pass opened the cold room. Their cooler contained the missing pudding."),
    Case("The planetarium remix", "Someone replaced the star show's soundtrack with duck noises between 19:40 and 19:42. Three crew members could access the console.", (
        ("Inspect the console", "The upload came from inside the locked control room. Remote uploads are disabled, and all three crew badges work."),
        ("Check the roof camera", "{a} is continuously visible maintaining the roof telescope from 19:35 to 19:50, five minutes from the console."),
        ("Review the foyer recording", "{b} leads a recorded welcome talk without leaving the foyer from 19:38 to 19:48."),
        ("Ask the projectionist", "The normal soundtrack played at 19:40; the changed file appeared at 19:42. There were no guests in the control room."),
    ), "{a} stayed on the roof and {b} stayed in the foyer. Only {c} could use the console during the upload window. The duck track was recovered from their USB drive."),
)

SUSPECT_NAMES = ("Pip", "Nova", "Ash", "Milo", "Clover", "Wren", "Jun", "Lumi")

# Each answer adds to an independent preference, not a good/bad score.
QUESTIONS = (
    ("The group chat has 300 unread messages.", ("Read the important threads", "Ask a friend for the highlights", "Send a perfectly mistimed meme")),
    ("Your team finds a mysterious button.", ("Check the manual", "Agree on a decision together", "Press it with a very long stick")),
    ("A dragon wants your lunch.", ("Negotiate a fair trade", "Share half and ask its name", "Offer yesterday's homework")),
    ("The server needs a mascot.", ("Compare everyone's suggestions", "Adopt the shy cat", "Nominate the broken printer")),
    ("You arrive early to a party.", ("Help finish the setup", "Find someone standing alone", "Test the disco lights")),
    ("Someone challenges you to karaoke.", ("Choose your reliable favourite", "Invite them to sing a duet", "Perform the loading music")),
    ("Your spaceship has one spare room.", ("Build a useful workshop", "Make a cosy shared lounge", "Install a zero-gravity ball pit")),
    ("A wizard offers one tiny power.", ("Always find your keys", "Make friends with nervous cats", "Summon a dramatic spotlight")),
    ("Your picnic is interrupted by rain.", ("Move to the shelter you spotted", "Make sure everyone stays warm", "Declare it a water-themed party")),
    ("A friend sends an unfinished story.", ("Help connect the plot threads", "Tell them what moved you", "Suggest a talking-fridge villain")),
    ("Your team wins a tiny trophy.", ("Set a new goal for next time", "Celebrate everyone's contribution", "Give a wildly dramatic speech")),
    ("You find a map to a secret garden.", ("Check the route and pack supplies", "Invite a friend who needs a break", "Wear a cape for the expedition")),
)

TRAITS = ("Strategy", "Connection", "Spontaneity")
PERSONALITIES = {
    (0,): ("The Pocket Strategist", "You turn a vague idea into a workable plan. Your friends can usually count on you to have packed the spare batteries."),
    (1,): ("The Cozy Diplomat", "You notice the person at the edge of the group. Your best plans tend to start with making everyone feel welcome."),
    (2,): ("The Plot Twist", "You bring curiosity and a willingness to try the unexpected. A dull afternoon rarely survives your arrival."),
    (0, 1): ("The Thoughtful Captain", "You pair practical plans with care for the people following them. Getting there matters; getting there together matters too."),
    (0, 2): ("The Calculated Chaos", "You enjoy surprising people, but there is often a plan behind the dramatic entrance. You pack supplies for your side quests."),
    (1, 2): ("The Spark Collector", "You turn spontaneous ideas into shared adventures. You are likely to invite the quiet friend into the fun."),
    (0, 1, 2): ("The Versatile Wildcard", "Your answers balance planning, connection and spontaneity. You choose the role the moment needs rather than sticking to one."),
}
