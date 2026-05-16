"""Channels module — Slack, Telegram, future Zalo."""
from app.channels.runner import ChannelMessage, ChannelResponse, handle_channel_message

__all__ = ["ChannelMessage", "ChannelResponse", "handle_channel_message"]
