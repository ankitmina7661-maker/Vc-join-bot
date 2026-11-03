# VC Join/Leave Bot

## Setup
1. `API_ID` / `API_HASH` → https://my.telegram.org
2. `BOT_TOKEN` → @BotFather
3. `SESSION_STRING` → ek *alag* Telegram account (assistant) ka Pyrogram string session
   (e.g. @StringFatherBot ya koi session generator se)
4. `.env.example` ko `.env` naam se copy karo aur values bharo
5. Install: `sudo apt install ffmpeg` (ya Termux: `pkg install ffmpeg`), phir
   `pip install -r requirements.txt`
6. Run: `python main.py`

## Group me
- Bot ko admin banao: **Delete messages** + **Invite users** permission
- Group me voice chat start karo
- `/vjoin` → assistant VC join karega
- `/vleave` → VC leave karega
- Command aur bot ka reply 5 sec me delete ho jate hain
