import asyncio
import os
import subprocess

from dotenv import load_dotenv
from pyrogram import Client, filters, idle, enums
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
SESSION_STRING = os.environ["SESSION_STRING"]  # assistant account
DELETE_AFTER = 5  # seconds

bot = Client("vcbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
assistant = Client(
    "assistant", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING
)
call = PyTgCalls(assistant)

SILENCE = "silence.mp3"


def make_silence():
    """Create a silent audio file (VC join karne ke liye ek stream chahiye)."""
    if not os.path.exists(SILENCE):
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anullsrc=r=48000:cl=stereo",
                "-t", "60", "-q:a", "9", SILENCE,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


# ---------- premium style messages ----------
def card(dot: str, title: str, lines: list[str]) -> str:
    body = "\n".join(f"└┈➤ {l}" for l in lines)
    return (
        f"{dot} <b>✦ {title} ✦</b>\n"
        f"<blockquote>{body}</blockquote>"
    )


def ok(title, *lines):
    return card("🟢", title, list(lines))


def err(title, *lines):
    return card("🔴", title, list(lines))


def info(title, *lines):
    return card("🔵", title, list(lines))


async def cleanup(*msgs: Message):
    await asyncio.sleep(DELETE_AFTER)
    for m in msgs:
        try:
            await m.delete()
        except Exception:
            pass


async def reply(message: Message, text: str):
    sent = await message.reply_text(text, parse_mode=enums.ParseMode.HTML)
    asyncio.create_task(cleanup(message, sent))


async def is_admin(message: Message) -> bool:
    if message.from_user is None:
        return False
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    )


async def ensure_assistant_in_chat(chat_id: int):
    me = await assistant.get_me()
    try:
        await bot.get_chat_member(chat_id, me.id)
        return
    except Exception:
        pass
    link = await bot.export_chat_invite_link(chat_id)  # bot ko invite perm chahiye
    await assistant.join_chat(link)


# ---------- commands ----------
@bot.on_message(filters.command("start"))
async def start(_, m: Message):
    await reply(
        m,
        info(
            "Welcome To VC Bot",
            "Group voice chat join/leave tool.",
            "Use /vjoin and /vleave in a group.",
        ),
    )


@bot.on_message(filters.command("vjoin") & filters.group)
async def vjoin(_, m: Message):
    if not await is_admin(m):
        return await reply(m, err("Denied", "Only group admins can use this."))
    try:
        await ensure_assistant_in_chat(m.chat.id)
    except Exception as e:
        return await reply(
            m,
            err(
                "Assistant Error",
                "Assistant group me add nahi ho paya.",
                "Bot ko admin banao (Invite Users permission).",
            ),
        )
    try:
        await call.play(
            m.chat.id,
            MediaStream(SILENCE, ffmpeg_parameters="-stream_loop -1"),
        )
        await reply(m, ok("Joined", "Voice chat join kar liya."))
    except Exception as e:
        name = type(e).__name__
        if name == "NoActiveGroupCall":
            await reply(m, err("No Voice Chat", "Pehle group me voice chat start karo."))
        elif name == "AlreadyJoinedError":
            await reply(m, info("Already Joined", "Bot pehle se VC me hai."))
        else:
            await reply(m, err("Failed", f"{name}"))


@bot.on_message(filters.command("vleave") & filters.group)
async def vleave(_, m: Message):
    if not await is_admin(m):
        return await reply(m, err("Denied", "Only group admins can use this."))
    try:
        await call.leave_call(m.chat.id)
        await reply(m, ok("Left", "Voice chat leave kar diya."))
    except Exception as e:
        name = type(e).__name__
        if name in ("NotInCallError", "NoActiveGroupCall"):
            await reply(m, info("Not In VC", "Bot VC me nahi hai."))
        else:
            await reply(m, err("Failed", f"{name}"))


async def main():
    make_silence()
    await bot.start()
    await assistant.start()
    await call.start()
    print("Bot is running...")
    await idle()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
