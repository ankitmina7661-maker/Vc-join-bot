import asyncio
import html
import json
import os
import shutil
import subprocess
import sys
import traceback

# Python 3.12+ me pyrogram import se pehle event loop chahiye
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from dotenv import load_dotenv
from pyrogram import Client, filters, idle, enums
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls import filters as fl
from pytgcalls.types import MediaStream

load_dotenv()


def env(*names: str) -> str:
    """Environment variable ko alag-alag naamo se padhta hai."""
    for n in names:
        v = os.environ.get(n)
        if v and v.strip():
            return v.strip()
    raise SystemExit(f"Environment variable missing: {' ya '.join(names)}")


API_ID = int(env("API_ID", "APP_ID"))
API_HASH = env("API_HASH", "APP_HASH")
BOT_TOKEN = env("BOT_TOKEN", "TOKEN")
SESSION_STRING = env("SESSION_STRING", "STRING_SESSION")
DELETE_AFTER = 5  # seconds

bot = Client(
    "vcbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True
)
assistant = Client(
    "assistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    in_memory=True,
)
call = PyTgCalls(assistant)

SILENCE = "silence.mp3"
DOWNLOADS = "downloads"
TARGETS_FILE = "targets.json"

active_chats: set[int] = set()  # jin groups ke VC me bot hai
current_file: dict[int, str] = {}  # chat_id -> abhi chal rahi downloaded file

ADMIN_STATUSES = (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)


def silent_stream() -> MediaStream:
    return MediaStream(SILENCE)


def make_silence():
    """Silent audio file banata hai (VC join karne ke liye ek stream chahiye)."""
    if os.path.exists(SILENCE):
        return
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg install nahi hai! Panel me ffmpeg install karo.")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anullsrc=r=48000:cl=stereo",
            "-t", "300", "-q:a", "9", SILENCE,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------- saved target groups ----------
try:
    with open(TARGETS_FILE) as f:
        targets: dict[int, int] = {int(k): v for k, v in json.load(f).items()}
except Exception:
    targets = {}


def set_target(user_id: int, chat_id: int):
    targets[user_id] = chat_id
    try:
        with open(TARGETS_FILE, "w") as f:
            json.dump(targets, f)
    except Exception:
        pass  # file save na ho to bhi bot chalta rahe


# ---------- premium style messages ----------
def card(dot: str, title: str, lines: list[str]) -> str:
    body = "\n".join(f"└┈➤ {l}" for l in lines)
    return f"{dot} <b>✦ {title} ✦</b>\n<blockquote>{body}</blockquote>"


def ok(title, *lines):
    return card("🟢", title, list(lines))


def err(title, *lines):
    return card("🔴", title, list(lines))


def info(title, *lines):
    return card("🔵", title, list(lines))


async def html_reply(m: Message, text: str) -> Message:
    return await m.reply_text(text, parse_mode=enums.ParseMode.HTML)


async def cleanup(*msgs: Message):
    await asyncio.sleep(DELETE_AFTER)
    for m in msgs:
        try:
            await m.delete()
        except Exception:
            pass


async def reply(message: Message, text: str):
    """Reply bhejo aur command + reply dono 5 sec me delete karo."""
    sent = await html_reply(message, text)
    asyncio.create_task(cleanup(message, sent))


async def is_admin_in(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ADMIN_STATUSES
    except Exception:
        return False


async def ensure_assistant_in_chat(chat_id: int):
    """Assistant account group me na ho to invite link se join karwata hai."""
    try:
        await assistant.get_chat_member(chat_id, "me")
        return
    except Exception:
        pass
    link = await bot.export_chat_invite_link(chat_id)  # bot ko Invite Users perm chahiye
    try:
        await assistant.join_chat(link)
    except Exception as e:
        if type(e).__name__ != "UserAlreadyParticipant":
            raise


# ---------- group commands ----------
@bot.on_message(filters.command("start"))
async def start(_, m: Message):
    await reply(
        m,
        info(
            "Welcome To VC Bot",
            "Group voice chat join/leave tool.",
            "Use /vjoin and /vleave in a group.",
            "Bot ke DM me audio bhejo, VC me play hoga.",
        ),
    )


@bot.on_message(filters.command("vjoin") & filters.group)
async def vjoin(_, m: Message):
    if m.from_user is None:
        return await reply(
            m, err("Denied", "Anonymous admin mode band karke try karo.")
        )
    if not await is_admin_in(m.chat.id, m.from_user.id):
        return await reply(m, err("Denied", "Only group admins can use this."))

    set_target(m.from_user.id, m.chat.id)  # DM audio isi group me chalega

    if m.chat.id in active_chats:
        return await reply(m, info("Already Joined", "Bot pehle se VC me hai."))

    try:
        await ensure_assistant_in_chat(m.chat.id)
    except Exception:
        return await reply(
            m,
            err(
                "Assistant Error",
                "Assistant group me add nahi ho paya.",
                "Bot ko admin banao (Invite Users permission).",
            ),
        )
    try:
        await call.play(m.chat.id, silent_stream())
        active_chats.add(m.chat.id)
        await reply(m, ok("Joined", "Voice chat join kar liya."))
    except Exception as e:
        name = type(e).__name__
        if name == "NoActiveGroupCall":
            await reply(m, err("No Voice Chat", "Pehle group me voice chat start karo."))
        else:
            traceback.print_exc()
            await reply(m, err("Failed", html.escape(name)))


@bot.on_message(filters.command("vleave") & filters.group)
async def vleave(_, m: Message):
    if m.from_user is None:
        return await reply(
            m, err("Denied", "Anonymous admin mode band karke try karo.")
        )
    if not await is_admin_in(m.chat.id, m.from_user.id):
        return await reply(m, err("Denied", "Only group admins can use this."))
    active_chats.discard(m.chat.id)
    old = current_file.pop(m.chat.id, None)
    if old and os.path.exists(old):
        try:
            os.remove(old)
        except Exception:
            pass
    try:
        await call.leave_call(m.chat.id)
        await reply(m, ok("Left", "Voice chat leave kar diya."))
    except Exception as e:
        name = type(e).__name__
        if name in ("NotInCallError", "NoActiveGroupCall"):
            await reply(m, info("Not In VC", "Bot VC me nahi hai."))
        else:
            traceback.print_exc()
            await reply(m, err("Failed", html.escape(name)))


# ---------- DM audio -> VC ----------
def _is_audio_doc(_, __, m: Message) -> bool:
    d = m.document
    return bool(d and d.mime_type and d.mime_type.startswith("audio"))


audio_filter = filters.private & (
    filters.audio | filters.voice | (filters.document & filters.create(_is_audio_doc))
)


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
    except ValueError:
        return await html_reply(m, err("Invalid", "Group ID number honi chahiye."))
    if not await is_admin_in(chat_id, m.from_user.id):
        return await html_reply(
            m,
            err(
                "Denied",
                "Group ID galat hai, bot us group me nahi hai,",
                "ya aap us group ke admin nahi ho.",
            ),
        )
    set_target(m.from_user.id, chat_id)
    await html_reply(
        m, ok("Target Set", f"Audio ab <code>{chat_id}</code> VC me chalega.")
    )


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
    if not await is_admin_in(chat_id, m.from_user.id):
        return await html_reply(m, err("Denied", "Aap us group ke admin nahi ho."))

    status = await html_reply(m, info("Downloading", "Audio download ho raha hai..."))
    try:
        os.makedirs(DOWNLOADS, exist_ok=True)
        path = await m.download(file_name=f"{DOWNLOADS}/")
        await ensure_assistant_in_chat(chat_id)
        await call.play(chat_id, MediaStream(path))
        active_chats.add(chat_id)

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
            ok(
                "Now Playing",
                html.escape(str(title)),
                "Assistant ID se VC me play ho raha hai.",
            ),
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        traceback.print_exc()
        name = type(e).__name__
        msg = (
            "Group me voice chat start karo."
            if name == "NoActiveGroupCall"
            else html.escape(name)
        )
        await status.edit_text(err("Failed", msg), parse_mode=enums.ParseMode.HTML)


@call.on_update(fl.stream_end())
async def on_stream_end(_, update):
    chat_id = update.chat_id
    f = current_file.pop(chat_id, None)
    if f and os.path.exists(f):
        try:
            os.remove(f)
        except Exception:
            pass
    if chat_id not in active_chats:
        return
    try:  # audio khatam -> silent stream pe wapas, taaki bot VC me bana rahe
        await call.play(chat_id, silent_stream())
    except Exception:
        traceback.print_exc()


async def main():
    make_silence()
    await bot.start()
    await assistant.start()
    # assistant ke groups cache me load karo (warna "Peer id invalid" aata hai)
    try:
        async for _ in assistant.get_dialogs():
            pass
    except Exception:
        traceback.print_exc()
    await call.start()
    print("Bot is running...", flush=True)
    await idle()


if __name__ == "__main__":
    try:
        print("Starting...", flush=True)
        loop.run_until_complete(main())
    except SystemExit as e:
        print(e, flush=True)
        raise
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
