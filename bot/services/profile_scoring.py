"""Deterministic profile weighting, priorities and recommendation templates."""

from dataclasses import replace
import logging

logger = logging.getLogger(__name__)

CATEGORIES = (
    ("readability", "avatar_score", "Readability"),
    ("cohesion", "styling_score", "Cohesion"),
    ("color_harmony", "harmony_score", "Color harmony"),
    ("detail_balance", "originality_score", "Detail balance"),
)

WEIGHT_PRESETS = {
    name: dict(zip((key for key, _, _ in CATEGORIES), weights, strict=True))
    for name, weights in {
        "avatar_only": (35, 10, 25, 30),
        "animated_avatar_only": (35, 10, 25, 30),
        "avatar_decoration": (30, 25, 25, 20),
        "avatar_nameplate": (35, 15, 25, 25),
        "avatar_banner": (30, 30, 25, 15),
        "avatar_banner_decoration": (25, 35, 25, 15),
        "avatar_banner_nameplate": (25, 35, 25, 15),
        "full_profile": (25, 35, 25, 15),
    }.items()
}


def detect_profile_elements(visual):
    return {
        "banner": bool(visual.banner or visual.banner_available or
                       (visual.accent_color is not None and not visual.banner_available)),
        "decoration": bool(visual.decoration or visual.has_decoration),
        "nameplate": visual.has_nameplate,
        "animated_avatar": visual.animated_avatar,
    }


def select_weight_preset(visual):
    elements = detect_profile_elements(visual)
    if elements["banner"]:
        if elements["decoration"] and elements["nameplate"]:
            return "full_profile"
        if elements["decoration"]:
            return "avatar_banner_decoration"
        if elements["nameplate"]:
            return "avatar_banner_nameplate"
        return "avatar_banner"
    if elements["decoration"]:
        return "avatar_decoration"
    if elements["nameplate"]:
        return "avatar_nameplate"
    return "animated_avatar_only" if elements["animated_avatar"] else "avatar_only"


def category_available(visual, field):
    return not (field in ("styling_score", "harmony_score") and visual.comparison_available is False)


def profilecheck_points(visual, weights=None):
    weights = WEIGHT_PRESETS[select_weight_preset(visual)] if weights is None else weights
    if set(weights) != {key for key, _, _ in CATEGORIES} or any(weight < 0 for weight in weights.values()) or sum(weights.values()) != 100:
        raise ValueError("Profile weights must cover all categories and sum to 100")
    return tuple((field, name, weights[key], (max(0, min(100, getattr(visual, field))) * weights[key] / 100) if category_available(visual, field) else 0)
                 for key, field, name in CATEGORIES)


def calculate_weighted_final_score(visual, weights=None):
    return max(0, min(100, round(sum(points for _, _, _, points in profilecheck_points(visual, weights)))))


def calculate_weighted_losses(visual, weights=None):
    # Sort before dividing by 100; ties retain the fixed category order.
    rows = profilecheck_points(visual, weights)
    order = sorted(range(len(rows)), key=lambda i: rows[i][2] * (100 - max(0, min(100, getattr(visual, rows[i][0])))), reverse=True)
    return tuple((rows[i][0], rows[i][1], rows[i][2] * (100 - max(0, min(100, getattr(visual, rows[i][0])))) / 100) for i in order)


def select_improvement_priority(visual, weights=None):
    # Recommendations follow the lowest visible score, independently of weight.
    field, name = min(((field, name) for _, field, name in CATEGORIES if category_available(visual, field)),
                      key=lambda item: max(0, min(100, getattr(visual, item[0]))))
    return field, name, max(0, min(100, getattr(visual, field)))


IMPROVEMENT_MESSAGES = {
    "avatar_score": {
        "low": "Make your PFP easier to see at small size. Increase the difference between the main subject and the background.",
        "medium": "Add a little more contrast around the main part of your PFP so it stands out better when small.",
        "high": "Your PFP is already clear. Just make sure the important details still show when it is displayed small.",
    },
    "styling_score": {
        "low": "Bring your {items} closer together by repeating the same main colors.",
        "medium": "Use one shared color across your {items}.",
        "high": "Most of your profile already matches. Fine-tune your {item} to match your PFP even better.",
    },
    "harmony_score": {
        "low": "Use fewer competing colors across your {items}. Stick to 2–3 main colors.",
        "medium": "Try repeating one main color between your PFP and {item} so they work better together.",
        "high": "Your colors already work well. Keep your {items} close to the same palette when updating them.",
    },
    "originality_score": {
        "low": "Your PFP has too much competing detail or not enough focus. Keep one clear main subject and simplify the area around it.",
        "medium": "Give the main part of your PFP a little more breathing room so it stands out better.",
        "high": "The detail level is already strong. Avoid adding anything that makes the PFP harder to read when small.",
    },
}


def get_score_band(score):
    return "low" if score < 60 else "medium" if score < 80 else "high"


def get_available_profile_items(visual):
    """Reuse detected equipment; don't claim effects/frames the API can't detect."""
    detected = detect_profile_elements(visual)
    items = []
    if visual.banner or visual.banner_available:
        items.append("Banner")
    elif detected["banner"]:
        items.append("Profile color")
    if detected["decoration"]:
        items.append("Avatar Decoration")
    if detected["nameplate"]:
        items.append("Nameplate")
    return items


def _join_items(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def get_best_profile_item_for_advice(items):
    # Prefer assets actually measured for colour matching; nameplates are metadata.
    return next((item for item in ("Banner", "Avatar Decoration", "Profile color", "Nameplate") if item in items), None)


def build_improvement_message(field, score, items):
    level = get_score_band(score)
    item = get_best_profile_item_for_advice(items)
    if field in ("styling_score", "harmony_score") and item is None:
        return "Best upgrade: Use fewer competing colors in your PFP and keep one clear main subject."
    message = IMPROVEMENT_MESSAGES[field][level].format(
        items=_join_items(["PFP", *items]), item=item)
    return "Best upgrade: " + message


def build_missing_comparison_message(visual):
    if not get_available_profile_items(visual):
        return "You only have a PFP right now, so there is no Banner or Avatar Decoration to compare it with."
    return "There are not enough profile items to compare yet."


def build_improvement_summary(visual):
    _, name, score = select_improvement_priority(visual)
    if score == 100:
        return "Every available category is 100/100."
    if visual.comparison_available is False:
        return build_missing_comparison_message(visual)
    return f"{name} needs the most work — {score}/100."


def get_rule_based_recommendation(visual):
    field, _, score = select_improvement_priority(visual)
    items = get_available_profile_items(visual)
    if score == 100:
        return "Best upgrade: Nothing major needs changing. Keep this balance when you update your " + _join_items(["PFP", *items]) + "."
    return build_improvement_message(field, score, items)


def finalize_profile_score(visual):
    reviewed = replace(visual, overall_score=calculate_weighted_final_score(visual))
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Profile preset: %s", select_weight_preset(reviewed))
        for field, name, weight, points in profilecheck_points(reviewed):
            logger.debug("%s score=%s weight=%s contribution=%.2f lost=%.2f", name,
                         getattr(reviewed, field), weight, points, weight - points)
        logger.debug("Final score: %s; Main improvement: %s", reviewed.overall_score,
                     select_improvement_priority(reviewed)[1])
    return reviewed
