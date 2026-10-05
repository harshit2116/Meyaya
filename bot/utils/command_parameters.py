"""Consistent public member labels without changing callback argument names."""

import re
from typing import get_args

import discord
from discord import app_commands
from discord.ext import commands


def member_annotation(annotation):
    return (
        annotation in (discord.Member, discord.User)
        or (isinstance(annotation, type) and issubclass(annotation, commands.MemberConverter))
        or any(member_annotation(arg) for arg in get_args(annotation))
    )


def normalize_member_parameters(bot):
    """Run after all cogs load, before syncing both generated and hybrid commands."""
    from bot.data.help_catalog import COMMANDS_BY_NAME

    for command in bot.tree.walk_commands():
        if not isinstance(command, app_commands.Command):
            continue
        members = [p for p in command.parameters if p.type == discord.AppCommandOptionType.user]
        if members:
            app_commands.rename(
                **{p.name: member_label(index, len(members)) for index, p in enumerate(members, 1)}
            )(command)
            app_commands.describe(
                **{
                    p.name: f"{'Optional ' if not p.required else ''}{member_label(index, len(members))} to use for this command."
                    for index, p in enumerate(members, 1)
                }
            )(command)
        entry = COMMANDS_BY_NAME.get(command.qualified_name)
        if entry:
            command.description = entry.description
    for command in bot.walk_commands():
        members = [p for p in command.params.values() if member_annotation(p.annotation)]
        index = 0
        for name, parameter in list(command.params.items()):
            if member_annotation(parameter.annotation):
                index += 1
                command.params[name] = parameter.replace(
                    displayed_name=member_label(index, len(members))
                )
        entry = COMMANDS_BY_NAME.get(command.qualified_name)
        if entry:
            command.help = entry.description
            command.description = entry.description


def member_label(index, total):
    return "member" if total == 1 else f"member{index}"


def member_usage(usage):
    """Give hand-written prefix examples the same ordered member labels."""
    index = 0
    pattern = r"([@<\[])(?:member\d*|first|second|third|fourth|fifth|other)(?=[\]>\s]|$)"
    total = len(re.findall(pattern, usage))

    def replace(match):
        nonlocal index
        index += 1
        return f"{match[1]}{member_label(index, total)}"

    return re.sub(
        pattern,
        replace,
        usage,
    )
