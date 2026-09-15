"""Clear, funny, built-in scenarios for Meyaya's anonymous social games."""

from __future__ import annotations

from dataclasses import dataclass
from secrets import SystemRandom


@dataclass(frozen=True, slots=True)
class GameScenario:
    theme: str
    prompt: str


SHOWDOWN_SCENARIOS = (
    GameScenario(
        "Last Slice Security",
        "Choose a fictional character to guard the last slice of pizza for thirty minutes while every rival choice tries to steal it. Explain why your guard wins.",
    ),
    GameScenario(
        "Group Project Captain",
        "Choose a fictional character to lead a group project due tomorrow. They must organize the team, finish the work, and outperform every rival captain.",
    ),
    GameScenario(
        "Road Trip Navigator",
        "Choose a fictional character to guide a road trip after every phone loses signal. They must reach the hotel before the rival navigators.",
    ),
    GameScenario(
        "Escape Room MVP",
        "Choose a fictional character as your escape room teammate. They have one hour to solve the clues faster than every rival choice.",
    ),
    GameScenario(
        "Cooking Contest Partner",
        "Choose a fictional character to help you cook dinner from random leftovers. Your meal must impress the judges more than every rival team's dish.",
    ),
    GameScenario(
        "Karaoke Champion",
        "Choose a fictional character for a karaoke contest where confidence matters more than singing skill. Explain how they steal the show from every rival.",
    ),
    GameScenario(
        "Babysitter of the Year",
        "Choose a fictional character to babysit three energetic children for one evening. They must keep everyone happy and cause less chaos than the rivals.",
    ),
    GameScenario(
        "Interview Coach",
        "Choose a fictional character to prepare you for an important job interview in one hour. Explain why their coaching beats every rival mentor.",
    ),
    GameScenario(
        "Hide-and-Seek Final",
        "Choose a fictional character for a city-wide game of hide-and-seek. They must remain hidden longer than every rival character without leaving town.",
    ),
    GameScenario(
        "Camping Teammate",
        "Choose a fictional character for a rainy weekend camping trip. They must keep the camp comfortable, cook dinner, and outperform every rival camper.",
    ),
    GameScenario(
        "Perfect Party Host",
        "Choose a fictional character to host a birthday party with almost no budget. Explain why guests would enjoy their party more than every rival event.",
    ),
    GameScenario(
        "Missing Cookie Mystery",
        "Choose a fictional character to solve who stole the last cookie from the kitchen. They must identify the culprit before every rival detective.",
    ),
    GameScenario(
        "Moving Day Hero",
        "Choose a fictional character to help you move apartments in one afternoon. They must pack safely, carry furniture, and beat every rival helper.",
    ),
    GameScenario(
        "Bargain Hunt",
        "Choose a fictional character to find the best deal during a crowded sale. They have a small budget and must outshop every rival choice.",
    ),
    GameScenario(
        "Game Night Champion",
        "Choose a fictional character for a board game tournament involving strategy, bluffing, and luck. Explain how they defeat every rival player.",
    ),
    GameScenario(
        "School Election Manager",
        "Choose a fictional character to manage your campaign for class president. They must create a convincing campaign without insulting any rival candidate.",
    ),
    GameScenario(
        "Pet-Sitting Professional",
        "Choose a fictional character to care for a stubborn cat and an excited puppy all weekend. They must do better than every rival sitter.",
    ),
    GameScenario(
        "Internet Outage Entertainer",
        "Choose a fictional character to entertain a bored household during a six-hour internet outage. Explain why nobody chooses a rival entertainer instead.",
    ),
    GameScenario(
        "Longest Queue Survivor",
        "Choose a fictional character to wait in a painfully slow queue without losing patience or their place. They must outlast every rival choice.",
    ),
    GameScenario(
        "Friendly Prank War",
        "Choose a fictional character for a harmless prank competition in the server house. Their prank must be funnier and kinder than every rival entry.",
    ),
    GameScenario(
        "Last-Minute Study Coach",
        "Choose a fictional character to help you study the night before an exam. They must explain the material better than every rival coach.",
    ),
    GameScenario(
        "Fashion Emergency",
        "Choose a fictional character to fix your outfit ten minutes before an important party. Explain why their solution beats every rival stylist.",
    ),
    GameScenario(
        "Birthday Gift Expert",
        "Choose a fictional character to select a thoughtful birthday gift for someone difficult to shop for. Their choice must beat every rival gift.",
    ),
    GameScenario(
        "Silent Snack Mission",
        "Choose a fictional character to retrieve snacks from the kitchen without waking a sleeping baby. They must finish more quietly than every rival choice.",
    ),
)


EXCUSE_SCENARIOS = (
    GameScenario(
        "Wrong Chat Message",
        "You sent a very embarrassing message to the main server instead of your friend. Give an excuse before everyone starts asking questions.",
    ),
    GameScenario(
        "The Missing Cake",
        "The birthday cake is missing, there are crumbs on your shirt, and you were seen near the fridge. Explain why you are innocent.",
    ),
    GameScenario(
        "Late Again",
        "You arrived forty minutes late after promising this time would be different. Give an excuse that might actually save your reputation.",
    ),
    GameScenario(
        "Camera Left On",
        "You forgot your camera was on during an online meeting and everyone saw your strange dance break. Explain what they witnessed.",
    ),
    GameScenario(
        "Forgot the Birthday",
        "You completely forgot your friend's birthday but posted online several times that day. Give an excuse that could earn forgiveness.",
    ),
    GameScenario(
        "Broken Office Chair",
        "The best chair in the room broke five minutes after you used it. Everyone is staring at you, so explain what happened.",
    ),
    GameScenario(
        "Accidental Reply All",
        "You used reply all on an email that was meant for one person and your comment was not flattering. Talk your way out.",
    ),
    GameScenario(
        "Empty Fridge Mystery",
        "Every shared snack disappeared overnight and your room contains all the empty wrappers. Give a convincing explanation for the evidence.",
    ),
    GameScenario(
        "Unfinished Homework",
        "Your assignment is completely blank, but you told everyone yesterday that it was already finished. Explain where the completed version went.",
    ),
    GameScenario(
        "Awkward Screenshot",
        "You accidentally sent someone a screenshot of their own message with your commentary visible. Give an excuse before they read it twice.",
    ),
    GameScenario(
        "Surprise Party Spoiler",
        "You revealed a surprise party while the guest of honor was standing behind you. Explain why your mistake was somehow helpful.",
    ),
    GameScenario(
        "Mystery Alarm",
        "Your alarm rang loudly during the quietest part of an important event. Explain why you had set it for that exact moment.",
    ),
    GameScenario(
        "Borrowed Hoodie",
        "You have been wearing your friend's missing hoodie for a week while insisting you never saw it. Explain the misunderstanding.",
    ),
    GameScenario(
        "Playlist Exposed",
        "Your private playlist started playing through the party speakers and the song choices are extremely embarrassing. Defend your musical reputation.",
    ),
    GameScenario(
        "The Group Chat Rename",
        "The group chat suddenly has an insulting new name, and the activity log says you changed it. Explain your decision.",
    ),
    GameScenario(
        "Coffee on the Notes",
        "You spilled coffee over the only copy of the presentation notes moments before it begins. Explain why this may improve the presentation.",
    ),
    GameScenario(
        "The Missing Keys",
        "Everyone has searched for the keys for an hour, and they are finally found inside your bag. Explain why this is not your fault.",
    ),
    GameScenario(
        "Delivery Next Door",
        "You accidentally sent an unusual online order to your neighbor's address. Explain the package before they decide to open it.",
    ),
    GameScenario(
        "Pajama Presentation",
        "You arrived at an important presentation wearing pajamas because you misunderstood one message. Give an excuse that sounds almost reasonable.",
    ),
    GameScenario(
        "Autocorrect Disaster",
        "Autocorrect changed your polite message into a dramatic insult and the recipient has already replied. Explain what you originally meant.",
    ),
    GameScenario(
        "Muted for Ten Minutes",
        "You delivered your entire online presentation while muted and ignored everyone waving at the screen. Explain why nobody should blame you.",
    ),
    GameScenario(
        "Lost Reservation",
        "You promised to book the restaurant, but the group arrived and no reservation exists. Give an excuse while everyone is still hungry.",
    ),
    GameScenario(
        "The Deleted Document",
        "The shared document disappeared immediately after you opened it, and the edit history shows your name. Explain what actually happened.",
    ),
    GameScenario(
        "Chair Reserved",
        "You took the only comfortable chair after being told it was reserved for someone else. Explain why moving now would be worse.",
    ),
)


SURVIVE_SCENARIOS = (
    GameScenario(
        "Locked in the Mall",
        "You are accidentally locked inside a shopping mall overnight with one friend and 10 percent phone battery. What is your practical survival plan?",
    ),
    GameScenario(
        "Rainy Camping Trip",
        "Heavy rain floods your campsite just before sunset, and the car is a thirty-minute walk away. How does your group handle the night?",
    ),
    GameScenario(
        "Road Trip Breakdown",
        "Your car breaks down on a quiet road, nobody has signal, and one passenger is already panicking. What is your plan?",
    ),
    GameScenario(
        "Airport Overnight",
        "Your flight is cancelled until morning, every nearby hotel is full, and your luggage is missing. How do you survive the night comfortably?",
    ),
    GameScenario(
        "Lost Without a Phone",
        "You are alone in an unfamiliar city when your phone dies and you cannot remember the hotel name. Explain your safest next steps.",
    ),
    GameScenario(
        "Dinner During a Blackout",
        "The power fails while you are cooking dinner for six guests, and the food is only half prepared. How do you rescue the evening?",
    ),
    GameScenario(
        "Escape Room Argument",
        "Your escape room team has stopped solving clues because everyone is arguing about the first puzzle. How do you get them moving again?",
    ),
    GameScenario(
        "Presentation Technology Failure",
        "Your laptop crashes at the start of an important presentation and no backup file will open. How do you finish without leaving?",
    ),
    GameScenario(
        "Separated at a Festival",
        "You lose your group at a crowded festival, your messages will not send, and the meeting point is blocked. What do you do?",
    ),
    GameScenario(
        "Wrong Turn on a Hike",
        "Your group realizes it followed the wrong hiking trail with two hours of daylight remaining. Explain how everyone gets back safely.",
    ),
    GameScenario(
        "Elevator Small Talk",
        "You are stuck in an elevator with a stranger who will not stop asking personal questions. How do you survive until help arrives?",
    ),
    GameScenario(
        "Babysitting Bedtime",
        "Three energetic children refuse to sleep, the parents return in one hour, and the living room is a disaster. What is your plan?",
    ),
    GameScenario(
        "Moving Day Rain",
        "It starts pouring during moving day while half the furniture is outside and the rental truck clock is running. How do you respond?",
    ),
    GameScenario(
        "Beach Bag Missing",
        "Your bag disappears during a beach trip with your phone, money, and hotel key inside. What is your calm and practical response?",
    ),
    GameScenario(
        "Hotel Booking Problem",
        "The hotel has no record of your booking, every room nearby is expensive, and it is almost midnight. How do you solve this?",
    ),
    GameScenario(
        "Missed the Last Train",
        "You miss the final train home after spending most of your money, and your friends live far away. What is your safest plan?",
    ),
    GameScenario(
        "Two Percent Battery",
        "Your phone has two percent battery while you wait for an important pickup in the wrong location. How do you make the battery count?",
    ),
    GameScenario(
        "Early Party Guest",
        "A surprise party guest arrives forty minutes early while decorations and the hidden cake are everywhere. How do you protect the surprise?",
    ),
    GameScenario(
        "Flat Tire Before a Wedding",
        "Your group gets a flat tire while dressed for a wedding that begins in forty-five minutes. Explain how everyone arrives presentably.",
    ),
    GameScenario(
        "Crowded Theme Park",
        "Your wallet goes missing at a crowded theme park and your group is already in different queues. What steps do you take first?",
    ),
    GameScenario(
        "Picnic Under Attack",
        "A swarm of bees discovers your picnic just as the food is served and one friend starts running. How do you save the day?",
    ),
    GameScenario(
        "Exam Morning Oversleep",
        "You wake up thirty minutes before an important exam, transport is delayed, and you still need your notes. What is your plan?",
    ),
    GameScenario(
        "Furniture Assembly Crisis",
        "Guests arrive in one hour, the new table is still in pieces, and the instructions make no sense. How do you prepare the room?",
    ),
    GameScenario(
        "Dinner Reservation Mix-Up",
        "Two friend groups arrive for dinner because you accidentally invited both to the same tiny table. How do you manage the evening?",
    ),
)


SCENARIOS = {
    "showdown": SHOWDOWN_SCENARIOS,
    "excuse": EXCUSE_SCENARIOS,
    "survive": SURVIVE_SCENARIOS,
}


def choose_scenario(
    game_type: str,
    *,
    rng: SystemRandom | None = None,
    exclude_theme: str | None = None,
) -> GameScenario:
    """Choose a local scenario without requiring an AI request."""

    pool = SCENARIOS.get(game_type)
    if pool is None:
        raise ValueError(f"Unknown social game type: {game_type}")
    choices = tuple(scenario for scenario in pool if scenario.theme != exclude_theme) or pool
    return (rng or SystemRandom()).choice(choices)
