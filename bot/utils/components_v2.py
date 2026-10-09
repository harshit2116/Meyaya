"""Shared native V2 cards and delivery for Meyaya's command interfaces.

Existing Embed builders remain presentation data; only LayoutView payloads go
to Discord. Interactive views keep their original items, callbacks and clocks.
"""

from __future__ import annotations

from functools import wraps
from contextvars import ContextVar
from itertools import groupby
from pathlib import PurePosixPath
from weakref import WeakValueDictionary

import discord

MISSING = discord.utils.MISSING
_message_views = WeakValueDictionary()
_installed = False
_delivering = ContextVar("meyaya_v2_delivery", default=False)


def _text_chunks(text, limit=2800):
    text = str(text)
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


def _display(text):
    return [discord.ui.TextDisplay(chunk) for chunk in _text_chunks(text)]


def _card_parts(content, embeds, media):
    parts = _display(content) if content else []
    referenced = set()
    color = 0xF48FB1
    for index, embed in enumerate(embeds):
        if index == 0 and embed.color is not None:
            color = embed.color.value
        if parts:
            parts.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        author = embed.author
        title = embed.title or ""
        if title and embed.url:
            title = f"[{title}]({embed.url})"
        heading = (f"-# {author.name}\n" if author.name else "") + (f"## {title}" if title else "")
        thumbnail = embed.thumbnail.url or author.icon_url
        text_parts = []
        if heading:
            text_parts.extend(_display(heading))
        if embed.description:
            text_parts.extend(_display(embed.description))
        for field in embed.fields:
            # Compact field headings keep result pages legible without the
            # large repeated headings of the old embed layout.
            text_parts.extend(_display(f"**{field.name}**\n{field.value}"))
        if thumbnail and text_parts:
            # The thumbnail sets a minimum Section height. Put the opening
            # body/fields alongside it rather than below a title-only Section,
            # which creates an avatar-height gap before the actual response.
            # Sections allow at most three displays; keep the group within one
            # page's text budget so pagination never splits this native unit.
            opening, size = [], 0
            while text_parts and len(opening) < 3 and size + len(text_parts[0].content) <= 3500:
                item = text_parts.pop(0)
                opening.append(item)
                size += len(item.content)
            parts.append(discord.ui.Section(*opening, accessory=discord.ui.Thumbnail(str(thumbnail))))
            referenced.add(str(thumbnail))
        elif thumbnail:
            # An image-only card still exposes its thumbnail at useful size.
            parts.append(discord.ui.MediaGallery(discord.MediaGalleryItem(str(thumbnail))))
            referenced.add(str(thumbnail))
        parts.extend(text_parts)
        if embed.image.url:
            parts.append(discord.ui.MediaGallery(discord.MediaGalleryItem(str(embed.image.url))))
            referenced.add(str(embed.image.url))
        footer = embed.footer.text or ""
        if embed.timestamp:
            footer += (" · " if footer else "") + f"<t:{int(embed.timestamp.timestamp())}:f>"
        if footer:
            parts.extend(_display("-# " + footer))
    for filename in media:
        url = "attachment://" + filename
        if url in referenced:
            continue
        if PurePosixPath(filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif"}:
            parts.append(discord.ui.MediaGallery(discord.MediaGalleryItem(url)))
        else:
            parts.append(discord.ui.File(url))
        referenced.add(url)
    return color, parts


def _text_length(item):
    if isinstance(item, discord.ui.TextDisplay):
        return len(item.content)
    return sum(_text_length(child) for child in getattr(item, "children", ()))


def _component_count(item):
    return 1 + sum(_component_count(child) for child in getattr(item, "children", ())) + (
        1 if isinstance(item, discord.ui.Section) else 0
    )


class MeyayaView(discord.ui.View, discord.ui.LayoutView):
    """LayoutView with the existing flat control API used by bot callbacks.

    View's row allocator and decorator collection keep all current controls on
    their original view. Only serialization groups them into native V2 rows.
    This avoids proxy views that would break item.view, stop(), wait(), or checks.
    """

    def __init__(self, *, timeout=180):
        self._card_content = None
        self._card_embeds = []
        self._card_media = []
        self._pages = [[]]
        self._page = 0
        self._accent = 0xF48FB1
        self._page_items = []
        super().__init__(timeout=timeout)

    def _is_layout(self):
        return True

    def has_components_v2(self):
        return True

    def present(self, *, content=MISSING, embeds=MISSING, media=MISSING):
        if content is not MISSING:
            self._card_content = str(content) if content is not None else None
        if embeds is not MISSING:
            self._card_embeds = [embed.copy() for embed in embeds]
            self._page = 0
        if media is not MISSING:
            self._card_media = list(media)
        self._rebuild_pages()
        return self

    def _control_rows(self):
        items = [child for child in self.children if child not in self._page_items]
        return [list(group) for _, group in groupby(
            sorted(items, key=lambda item: item._rendered_row or 0),
            key=lambda item: item._rendered_row or 0,
        )]

    def _rebuild_pages(self):
        for item in self._page_items:
            discord.ui.LayoutView.remove_item(self, item)
        self._page_items = []
        self._accent, parts = _card_parts(self._card_content, self._card_embeds, self._card_media)
        rows = self._control_rows()
        # Reserve a container plus a navigation row with three buttons. All
        # nested controls count against Discord's 40-component message ceiling.
        budget = 40 - sum(len(row) + 1 for row in rows) - 5
        self._pages = []
        page, text_size, count = [], 0, 0
        for part in parts:
            size, cost = _text_length(part), _component_count(part)
            if page and (text_size + size > 3500 or count + cost > budget or len(page) >= 9):
                self._pages.append(page)
                page, text_size, count = [], 0, 0
            page.append(part)
            text_size += size
            count += cost
        self._pages.append(page)
        self._page = min(self._page, len(self._pages) - 1)
        if len(self._pages) > 1:
            for action, label in (("prev", "Previous"), ("position", "Page"), ("next", "Next")):
                button = discord.ui.Button(label=label, custom_id=f"meyaya:pages:{self.id}:{action}")

                async def navigate(interaction, action=action):
                    if self.is_finished():
                        await interaction.response.send_message("This menu has expired. Open the command again.", ephemeral=True)
                        return
                    self._page = max(0, min(len(self._pages) - 1, self._page + (-1 if action == "prev" else 1)))
                    await interaction.response.edit_message(view=self)

                button.callback = navigate
                # Pagination uses an additional V2 row even when all five
                # classic control rows are occupied. Existing rows stay intact.
                discord.ui.LayoutView.add_item(self, button)
                self._page_items.append(button)

    def to_components(self):
        # Controls can be added/removed by an existing callback before an edit.
        # Recalculate capacity without resetting the currently selected page.
        self._rebuild_pages()
        parts = self._pages[self._page]
        container = discord.ui.Container(*(part.copy() for part in parts), accent_color=discord.Colour(self._accent))
        if not parts:
            container.add_item(discord.ui.TextDisplay("\u200b"))
        result = [container.to_component_dict()]
        for row in self._control_rows():
            result.append({"type": 1, "components": [item.to_component_dict() for item in row]})
        if self._page_items:
            previous, position, following = self._page_items
            previous.disabled = self._page == 0 or self.is_finished()
            position.label = f"{self._page + 1} / {len(self._pages)}"
            position.disabled = True
            following.disabled = self._page + 1 == len(self._pages) or self.is_finished()
            result.append({"type": 1, "components": [item.to_component_dict() for item in self._page_items]})
        return result

    def content_length(self):
        return sum(_text_length(part) for part in self._pages[self._page])


def _message_for(receiver):
    if isinstance(receiver, (discord.Message, discord.PartialMessage)):
        return receiver
    interaction = getattr(receiver, "_parent", receiver)
    return getattr(interaction, "message", None)


def _frozen_message(message):
    view = discord.ui.LayoutView.from_message(message)
    for item in view.walk_children():
        if isinstance(item, (discord.ui.Button, discord.ui.Select)):
            item.disabled = True
    view.stop()
    return view


def v2_payload(kwargs, *, previous=None, force=False, editing=False):
    """Normalize one send/edit without changing visibility or file ownership."""
    # Library forwarding methods explicitly pass MISSING for omitted options.
    # Treat those as absent so view-only webhook edits retain their card data.
    result = {key: value for key, value in kwargs.items() if value is not MISSING}
    view = result.get("view", MISSING)
    # Context.send forwards its default None values to channel/interaction
    # send methods. A second normalization must not erase the prepared card.
    if not editing and isinstance(view, MeyayaView):
        for key in ("embed", "embeds", "content"):
            if result.get(key, MISSING) is None:
                result.pop(key, None)
    embeds = result.get("embeds", MISSING)
    embed = result.get("embed", MISSING)
    if embed not in (MISSING, None) and embeds not in (MISSING, None):
        raise TypeError("Cannot mix embed and embeds keyword arguments.")
    has_embed = embed not in (MISSING, None) or bool(embeds not in (MISSING, None) and embeds)
    # Bespoke LayoutViews (including the dungeon HUD) already own their layout.
    if isinstance(view, discord.ui.LayoutView) and not isinstance(view, MeyayaView):
        if has_embed:
            raise ValueError("Native V2 views cannot be combined with classic embeds.")
        return result
    cached = _message_views.get(getattr(previous, "id", None))
    if view is MISSING and cached is not None:
        view = cached
    previous_v2 = bool(getattr(getattr(previous, "flags", None), "components_v2", False))
    files = []
    for key in ("files", "attachments"):
        files.extend(result.get(key) or [])
    if result.get("file"):
        files.append(result["file"])
    structured = has_embed or isinstance(view, MeyayaView) or previous_v2 or (
        force and (result.get("content") is not None or files)
    )
    if not structured or result.get("poll") is not None or result.get("stickers"):
        return result
    if view is None and not has_embed and "content" not in result and previous_v2:
        result["view"] = _frozen_message(previous)
        result.pop("embed", None)
        result.pop("embeds", None)
        return result
    if view is MISSING and previous_v2 and cached is None and not has_embed and "content" not in result:
        return result
    if view in (MISSING, None):
        view = MeyayaView()
    if not isinstance(view, MeyayaView):
        raise TypeError("Migrate this interactive view to MeyayaView before sending a V2 card.")
    # Embed text never notified mentioned users. Preserve that behavior when
    # promoting its text into native components, including later page changes.
    if has_embed and not result.get("content") and result.get("allowed_mentions") is None:
        result["allowed_mentions"] = discord.AllowedMentions.none()
    updates = {}
    if "content" in result:
        updates["content"] = result.pop("content")
    if "embed" in result or "embeds" in result:
        updates["embeds"] = list(embeds or []) if embeds is not MISSING else ([embed] if embed else [])
    if files or "attachments" in result:
        updates["media"] = [file.filename for file in files]
    view.present(**updates)
    result.pop("embed", None)
    result.pop("embeds", None)
    result["view"] = view
    if editing:
        result.update(content=None, embeds=[])
    return result


def _remember(result, view):
    if not isinstance(view, MeyayaView):
        return
    message_id = getattr(result, "id", None) or getattr(result, "message_id", None)
    if message_id is not None:
        _message_views[message_id] = view


def install_components_v2():
    """Install once at bot startup across channel, DM and interaction delivery."""
    global _installed
    if _installed:
        return
    import inspect
    targets = (
        (discord.abc.Messageable, "send", False, False),
        (discord.Message, "edit", True, False),
        (discord.PartialMessage, "edit", True, False),
        (discord.WebhookMessage, "edit", True, False),
        (discord.InteractionMessage, "edit", True, False),
        (discord.InteractionResponse, "send_message", False, True),
        (discord.InteractionResponse, "edit_message", True, False),
        (discord.Interaction, "edit_original_response", True, False),
        (discord.Webhook, "send", False, False),
        (discord.Webhook, "edit_message", True, False),
    )
    for cls, name, editing, force in targets:
        original = getattr(cls, name)
        signature = inspect.signature(original)

        def wrap(original, signature, editing, force):
            @wraps(original)
            async def deliver(receiver, *args, **kwargs):
                # WebhookMessage/InteractionMessage delegate edits to another
                # patched transport. Normalize once, at the outermost call.
                if _delivering.get():
                    return await original(receiver, *args, **kwargs)
                bound = signature.bind_partial(receiver, *args, **kwargs)
                receiver_name = next(iter(signature.parameters))
                values = {key: value for key, value in bound.arguments.items() if key != receiver_name}
                previous = _message_for(receiver)
                # Webhook edits carry a message ID without a Message object.
                if previous is None and "message_id" in values:
                    cached = _message_views.get(values["message_id"])
                    if cached is not None and values.get("view", MISSING) is MISSING:
                        values["view"] = cached
                application_followup = (
                    isinstance(receiver, discord.Webhook)
                    and receiver.type is discord.WebhookType.application
                    and not editing
                )
                values = v2_payload(values, previous=previous, force=force or application_followup, editing=editing)
                bound.arguments.clear()
                bound.arguments[receiver_name] = receiver
                bound.arguments.update(values)
                token = _delivering.set(True)
                try:
                    result = await original(*bound.args, **bound.kwargs)
                finally:
                    _delivering.reset(token)
                _remember(result, values.get("view"))
                return result
            return deliver

        setattr(cls, name, wrap(original, signature, editing, force))
    _installed = True
