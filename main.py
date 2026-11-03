import asyncio
import json
import os
import subprocess

from dotenv import load_dotenv
from pyrogram import Client, filters, idle, enums
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls import filters as fl
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
    set_target(m.from_user.id, m.chat.id)  # DM audio isi group me chalega
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


# ---------- DM audio -> VC ----------
DOWNLOADS = "downloads"
TARGETS_FILE = "targets.json"
current_file: dict[int, str] = {}

try:
    with open(TARGETS_FILE) as f:
        targets: dict[int, int] = {int(k): v for k, v in json.load(f).items()}
except Exception:
    targets = {}


def set_target(user_id: int, chat_id: int):
    targets[user_id] = chat_id
    with open(TARGETS_FILE, "w") as f:
        json.dump(targets, f)


def _is_audio_doc(_, __, m: Message) -> bool:
    d = m.document
    return bool(d and d.mime_type and d.mime_type.startswith("audio"))


audio_filter = filters.private & (
    filters.audio | filters.voice | (filters.document & filters.create(_is_audio_doc))
)


async def html_reply(m: Message, text: str) -> Message:
    return await m.reply_text(text, parse_mode=enums.ParseMode.HTML)


@bot.on_message(filters.command("setvc") & filters.private)
async def setvc(_, m: Message):
    if len(m.command) < 2:
        return await html_reply(
            m,
            info(
                "Set Target VC",
                "Usage: /setvc -100xxxxxxxxxx",
                "Ya group me /vjoin likho, auto set ho jayega.",
            ),
        )
    try:
        chat_id = int(m.command[1])
        member = await bot.get_chat_member(chat_id, m.from_user.id)
        if member.status not in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        ):
            return await html_reply(m, err("Denied", "Aap us group ke admin nahi ho."))
    except Exception:
        return await html_reply(
            m, err("Invalid", "Group ID galat hai ya bot us group me nahi hai.")
        )
    set_target(m.from_user.id, chat_id)
    await html_reply(m, ok("Target Set", f"Audio ab <code>{chat_id}</code> VC me chalega."))


@bot.on_message(audio_filter)
async def dm_audio(_, m: Message):
    chat_id = targets.get(m.from_user.id)
    if not chat_id:
        return await html_reply(
            m,
            err(
                "No Target",
                "Pehle group me /vjoin likho",
                "ya DM me /setvc &lt;group_id&gt; use karo.",
            ),
        )
    # abhi bhi admin hai ya nahi
    try:
        member = await bot.get_chat_member(chat_id, m.from_user.id)
        if member.status not in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        ):
            return await html_reply(m, err("Denied", "Aap us group ke admin nahi ho."))
    except Exception:
        return await html_reply(m, err("Error", "Target group access nahi ho raha."))

    status = await html_reply(m, info("Downloading", "Audio download ho raha hai..."))
    try:
        os.makedirs(DOWNLOADS, exist_ok=True)
        path = await m.download(file_name=f"{DOWNLOADS}/")
        await ensure_assistant_in_chat(chat_id)
        await call.play(chat_id, MediaStream(path))

        old = current_file.get(chat_id)
        current_file[chat_id] = path
        if old and old != path and os.path.exists(old):
            os.remove(old)

        title = (
            (m.audio and (m.audio.title or m.audio.file_name))
            or (m.document and m.document.file_name)
            or "Voice Message"
        )
        await status.edit_text(
            ok("Now Playing", f"{title}", "Assistant ID se VC me play ho raha hai."),
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        name = type(e).__name__
        msg = (
            "Group me voice chat start karo."
            if name == "NoActiveGroupCall"
            else name
        )
        await status.edit_text(err("Failed", msg), parse_mode=enums.ParseMode.HTML)


@call.on_update(fl.stream_end())
async def on_stream_end(_, update):
    chat_id = update.chat_id
    f = current_file.pop(chat_id, None)
    if f and os.path.exists(f):
        os.remove(f)
    try:  # audio khatam -> VC me silent stream pe wapas, taaki bot VC me bana rahe
        await call.play(
            chat_id, MediaStream(SILENCE, ffmpeg_parameters="-stream_loop -1")
        )
    except Exception:
        pass


async def main():
    make_silence()
    await bot.start()
    await assistant.start()
    await call.start()
    print("Bot is running...")
    await idle()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
