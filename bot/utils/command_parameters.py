"""Consistent public member labels without changing callback argument names."""

import re
from typing import get_args

import discord
from discord import app_commands


def member_annotation(annotation):
    return annotation in (discord.Member, discord.User) or any(
        member_annotation(arg) for arg in get_args(annotation)
    )


def normalize_member_parameters(bot):
    """Run after all cogs load, before syncing both generated and hybrid commands."""
    for command in bot.tree.walk_commands():
        if not isinstance(command, app_commands.Command):
            continue
        members = [p for p in command.parameters if p.type == discord.AppCommandOptionType.user]
        if members:
            app_commands.rename(**{
                p.name: f"member{index}" for index, p in enumerate(members, 1)
            })(command)
    for command in bot.walk_commands():
        index = 0
        for name, parameter in list(command.params.items()):
            if member_annotation(parameter.annotation):
                index += 1
                command.params[name] = parameter.replace(displayed_name=f"member{index}")


def member_usage(usage):
    """Give hand-written prefix examples the same ordered member labels."""
    index = 0

    def replace(match):
        nonlocal index
        index += 1
        return f"{match[1]}member{index}"

    return re.sub(
        r"([@<\[])(?:member|first|second|third|fourth|fifth|other)(?=[\]>\s]|$)",
        replace, usage,
    )
