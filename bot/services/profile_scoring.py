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
        "low": "Strengthen the subject's light/dark contrast so it reads at icon size.",
        "medium": "Separate the subject from its background with a little more contrast.",
        "high": "Keep the focal contrast clear when previewing your avatar at icon size.",
    },
    "styling_score": {
        "low": "Bring the avatar, backdrop and decoration into one consistent palette.",
        "medium": "Repeat one avatar accent across the backdrop and decoration.",
        "high": "Fine-tune the least matching accent across your profile elements.",
    },
    "harmony_score": {
        "low": "Simplify competing colours and choose one dominant palette.",
        "medium": "Reduce the strongest colour mismatch while keeping one accent.",
        "high": "Keep your accents consistent and refine the remaining colour contrast.",
    },
    "originality_score": {
        "low": "Keep recognisable focal detail without crowding the small avatar.",
        "medium": "Balance the focal detail with quieter areas around it.",
        "high": "Keep defining details readable when the avatar is displayed small.",
    },
}


def get_rule_based_recommendation(visual):
    field, _, _ = select_improvement_priority(visual)
    score = max(0, min(100, getattr(visual, field)))
    level = "low" if score < 60 else "medium" if score < 80 else "high"
    message = IMPROVEMENT_MESSAGES[field][level]
    return "Best upgrade: " + message


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
