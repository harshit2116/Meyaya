"""Court invitation, evidence, and statement UI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

from bot.app import MeyayaBot
from bot.models.court import CourtCase
from bot.services.court import CourtError, CourtService, CourtStatus, court_case_lock
from bot.utils.embeds import meyaya_embed

CourtJudgeCallback = Callable[[int, discord.Interaction, discord.Message, bool], Awaitable[None]]


def build_court_embed(case: CourtCase) -> discord.Embed:
    status_labels = {
        CourtStatus.LOCKED: "Statements locked - ready to retry judging",
        CourtStatus.PENDING: "Waiting for the defendant",
        CourtStatus.COLLECTING: "Collecting statements",
        CourtStatus.JUDGING: "Meyaya is judging",
        CourtStatus.CLARIFYING: "Waiting for one follow-up answer",
        CourtStatus.COMPLETED: "Verdict delivered",
        CourtStatus.CLOSED: "Case closed",
    }
    embed = meyaya_embed(
        f"Meyaya Court - Case #{case.id}",
        f"**Charge**\n{case.charge}",
        tone="magic",
        icon="⚖️",
    )
    embed.add_field(name="Plaintiff", value=f"<@{case.plaintiff_id}>", inline=True)
    embed.add_field(name="Defendant", value=f"<@{case.defendant_id}>", inline=True)
    embed.add_field(
        name="Status",
        value=status_labels.get(CourtStatus(case.status), case.status),
        inline=False,
    )
    registered = list(case.registered_witness_ids or [])
    if case.status == CourtStatus.PENDING:
        witness_list = (
            "\n".join(f"- <@{user_id}>" for user_id in registered)
            if registered
            else "No witnesses registered yet."
        )
        embed.add_field(
            name=f"Registered witnesses - {len(registered)}/5",
            value=witness_list,
            inline=False,
        )
        embed.add_field(
            name="Before the case starts",
            value=(
                "The defendant may accept or decline. Other members may register as witnesses "
                "now. Registration closes when the case is accepted."
            ),
            inline=False,
        )
    if case.status == CourtStatus.COLLECTING:
        witness_statements = len(case.witness_statements or {})
        embed.add_field(
            name="Evidence progress",
            value=(
                f"Plaintiff statement: {'Ready' if case.plaintiff_statement else 'Missing'}\n"
                f"Defendant statement: {'Ready' if case.defendant_statement else 'Missing'}\n"
                f"Registered witness statements: {witness_statements}/{len(registered)}"
            ),
            inline=False,
        )
    if case.status == CourtStatus.CLARIFYING:
        answers = case.clarification_answers or {}
        target = case.clarification_target or "required party"
        required_roles = ("plaintiff", "defendant") if target == "both" else (target,)
        answer_progress = "\n".join(
            f"{role.title()}: {'Ready' if role in answers else 'Waiting'}"
            for role in required_roles
        )
        embed.add_field(
            name="Meyaya needs one detail",
            value=f"**Question for {target}:**\n{case.clarification_question}",
            inline=False,
        )
        embed.add_field(
            name="Answer progress",
            value=answer_progress,
            inline=False,
        )
    return embed


async def _send_next_stage(
    old_message: discord.Message,
    case: CourtCase,
    view: discord.ui.View | None,
) -> discord.Message:
    """Close an old operation message and publish the next state as a new embed."""

    try:
        await old_message.edit(view=None)
    except discord.HTTPException:
        pass
    message = await old_message.channel.send(
        embed=build_court_embed(case),
        view=view,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if view is not None and hasattr(view, "message"):
        view.message = message
    return message


class CourtStatementModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        bot: MeyayaBot,
        case_id: int,
        statement_type: str,
        public_message: discord.Message,
        judge_callback: CourtJudgeCallback,
    ) -> None:
        titles = {
            "plaintiff": "Plaintiff statement",
            "defendant": "Defendant statement",
            "witness": "Witness statement",
            "clarification": "Follow-up answer",
        }
        super().__init__(title=titles[statement_type], timeout=300)
        self.bot = bot
        self.case_id = case_id
        self.statement_type = statement_type
        self.public_message = public_message
        self.judge_callback = judge_callback
        self.statement = discord.ui.TextInput(
            label="Your statement",
            style=discord.TextStyle.paragraph,
            min_length=1,
            max_length=1200,
            placeholder="Tell Meyaya your side of the story.",
        )
        self.add_item(self.statement)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            async with court_case_lock(self.case_id):
                async with self.bot.db_session() as session:
                    service = CourtService(session)
                    if self.statement_type == "witness":
                        case = await service.submit_witness(
                            self.case_id,
                            interaction.user.id,
                            str(self.statement),
                        )
                    elif self.statement_type == "clarification":
                        case = await service.submit_clarification(
                            self.case_id,
                            interaction.user.id,
                            str(self.statement),
                        )
                    else:
                        case = await service.submit_statement(
                            self.case_id,
                            interaction.user.id,
                            str(self.statement),
                        )
        except CourtError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        recorded_item = "answer" if self.statement_type == "clarification" else "statement"
        await interaction.response.send_message(
            f"Your {recorded_item} has been recorded.", ephemeral=True
        )
        should_auto_judge = (
            self.statement_type in {"plaintiff", "defendant"}
            and bool(case.plaintiff_statement)
            and bool(case.defendant_statement)
            and not case.registered_witness_ids
        )
        if should_auto_judge:
            await self.judge_callback(
                self.case_id,
                interaction,
                self.public_message,
                True,
            )
            return
        if case.status == CourtStatus.CLARIFYING:
            next_view: discord.ui.View = CourtClarificationView(
                bot=self.bot,
                case_id=self.case_id,
                judge_callback=self.judge_callback,
            )
        else:
            next_view = CourtCollectionView(
                bot=self.bot,
                case_id=self.case_id,
                judge_callback=self.judge_callback,
            )
        await _send_next_stage(self.public_message, case, next_view)


class CourtInvitationView(discord.ui.View):
    def __init__(
        self, *, bot: MeyayaBot, case_id: int, defendant_id: int, judge_callback: CourtJudgeCallback
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.case_id = case_id
        self.defendant_id = defendant_id
        self.judge_callback = judge_callback
        self.message: discord.Message | None = None

    @discord.ui.button(label="Accept case", emoji="⚖️", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            async with court_case_lock(self.case_id):
                async with self.bot.db_session() as session:
                    case = await CourtService(session).accept(self.case_id, interaction.user.id)
        except CourtError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        collection = CourtCollectionView(
            bot=self.bot,
            case_id=self.case_id,
            judge_callback=self.judge_callback,
        )
        self.stop()
        await interaction.response.edit_message(view=None)
        if interaction.message is not None:
            await _send_next_stage(interaction.message, case, collection)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            async with court_case_lock(self.case_id):
                async with self.bot.db_session() as session:
                    case = await CourtService(session).decline(self.case_id, interaction.user.id)
        except CourtError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(view=None)
        if interaction.message is not None:
            await _send_next_stage(interaction.message, case, None)

    @discord.ui.button(label="Register as witness", emoji="📝", style=discord.ButtonStyle.secondary)
    async def register_witness(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        try:
            async with court_case_lock(self.case_id):
                async with self.bot.db_session() as session:
                    case = await CourtService(session).register_witness(
                        self.case_id, interaction.user.id
                    )
        except CourtError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        next_view = CourtInvitationView(
            bot=self.bot,
            case_id=self.case_id,
            defendant_id=self.defendant_id,
            judge_callback=self.judge_callback,
        )
        self.stop()
        await interaction.response.edit_message(view=None)
        if interaction.message is not None:
            await _send_next_stage(interaction.message, case, next_view)

    async def on_timeout(self) -> None:
        try:
            async with self.bot.db_session() as session:
                case = await CourtService(session).expire(self.case_id, (CourtStatus.PENDING,))
        except CourtError:
            return
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(embed=build_court_embed(case), view=self)
            except discord.HTTPException:
                pass


class CourtCollectionView(discord.ui.View):
    def __init__(self, *, bot: MeyayaBot, case_id: int, judge_callback: CourtJudgeCallback) -> None:
        super().__init__(timeout=1800)
        self.bot = bot
        self.case_id = case_id
        self.judge_callback = judge_callback
        self.message: discord.Message | None = None

    async def _open_modal(self, interaction: discord.Interaction, statement_type: str) -> None:
        if interaction.message is None:
            await interaction.response.send_message(
                "The court message is unavailable.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            CourtStatementModal(
                bot=self.bot,
                case_id=self.case_id,
                statement_type=statement_type,
                public_message=interaction.message,
                judge_callback=self.judge_callback,
            )
        )

    @discord.ui.button(label="Plaintiff statement", style=discord.ButtonStyle.primary)
    async def plaintiff(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_modal(interaction, "plaintiff")

    @discord.ui.button(label="Defendant statement", style=discord.ButtonStyle.primary)
    async def defendant(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_modal(interaction, "defendant")

    @discord.ui.button(label="Witness statement", style=discord.ButtonStyle.secondary)
    async def witness(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_modal(interaction, "witness")

    @discord.ui.button(label="Lock and judge", emoji="🔒", style=discord.ButtonStyle.success)
    async def judge(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.message is None:
            await interaction.response.send_message(
                "The court message is unavailable.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await self.judge_callback(self.case_id, interaction, interaction.message, False)

    async def on_timeout(self) -> None:
        try:
            async with self.bot.db_session() as session:
                case = await CourtService(session).expire(self.case_id, (CourtStatus.COLLECTING, CourtStatus.LOCKED))
        except CourtError:
            return
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(embed=build_court_embed(case), view=self)
            except discord.HTTPException:
                pass


class CourtClarificationView(discord.ui.View):
    """Collect one targeted follow-up before the final judgement."""

    def __init__(self, *, bot: MeyayaBot, case_id: int, judge_callback: CourtJudgeCallback) -> None:
        super().__init__(timeout=1800)
        self.bot = bot
        self.case_id = case_id
        self.judge_callback = judge_callback
        self.message: discord.Message | None = None

    @discord.ui.button(label="Answer follow-up", emoji="💬", style=discord.ButtonStyle.primary)
    async def answer(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.message is None:
            await interaction.response.send_message(
                "The court message is unavailable.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            CourtStatementModal(
                bot=self.bot,
                case_id=self.case_id,
                statement_type="clarification",
                public_message=interaction.message,
                judge_callback=self.judge_callback,
            )
        )

    @discord.ui.button(label="Continue to verdict", emoji="⚖️", style=discord.ButtonStyle.success)
    async def judge(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.message is None:
            await interaction.response.send_message(
                "The court message is unavailable.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await self.judge_callback(self.case_id, interaction, interaction.message, False)

    async def on_timeout(self) -> None:
        try:
            async with self.bot.db_session() as session:
                case = await CourtService(session).expire(self.case_id, (CourtStatus.CLARIFYING,))
        except CourtError:
            return
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(embed=build_court_embed(case), view=self)
            except discord.HTTPException:
                pass
