import logging
import qrcode
from PIL import Image
import io
import requests
import random
import string
import asyncio
from datetime import date

from pymongo import MongoClient
from bson.binary import Binary

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# --- MongoDB Configuration ---
MONGO_URI = 'mongodb+srv://wenoobhost1:WBOEXfFslsyXY1nN@cluster0.7ioby.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'
client = MongoClient(MONGO_URI)
db = client['Cluster0']
user_messages_collection = db['user_messages']
qr_codes_collection = db['qr_codes']
user_tn_codes_collection = db['user_tn_codes']

# --- Bot Configuration ---
BOT_TOKEN = '7240000536:AAG4ddU8TAW28N7PcywJZHZjMMJuRt8AaGE'
CHANNEL_ID = -1002301680804           # Transaction channel (tr db)
INLINE_BUTTON_CHANNEL = -1002315192547  # Inline button channel for user ID
ADMIN_USER_ID = 7144181041

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Usage Statistics (In-Memory) ---
unique_users_total = set()
unique_users_today = set()
user_usage_date = {}  # mapping: user_id -> date

def generate_unique_code(length=10):
    return 'IT' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def download_logo_from_telegram(file_id):
    bot_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/'
    file_info = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}').json()
    file_path = file_info['result']['file_path']
    response = requests.get(bot_url + file_path)
    return response.content

def generate_qr_code(data, logo_file_id=None):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    if logo_file_id:
        try:
            logo_content = download_logo_from_telegram(logo_file_id)
            logo = Image.open(io.BytesIO(logo_content)).convert("RGBA")
            logo.thumbnail((50, 50))
            img = img.convert("RGBA")
            logo_position = ((img.size[0] - logo.size[0]) // 2, (img.size[1] - logo.size[1]) // 2)
            img.paste(logo, logo_position, mask=logo)
        except Exception as e:
            logging.error(f"Error adding logo to QR code: {e}")
    return img

# Define a set of file IDs that should be sent as videos.
VIDEO_FILE_IDS = {
    "BAACAgUAAxkBAAJ5bWfcAAFscCgDEwLE_ZVKf-j-LYqoaQACQxgAAtjV6FIFkb7AFYpZxjYE",
    "BAACAgUAAxkBAAMHZuLGLkRq4Ej1PekdoULAdoyIeMUAAnEVAALsLxBXCdaESjhVUag2BA"
}

async def start(update: Update, context):
    user_id = update.message.from_user.id
    args = context.args

    # --- Update Usage Stats ---
    today = date.today()
    unique_users_total.add(user_id)
    if user_usage_date.get(user_id) != today:
        unique_users_today.add(user_id)
        user_usage_date[user_id] = today

    # Normalize parameter input so that both uppercase and lowercase 's' behave the same.
    if args and args[0].lower() == 's':
        # If you need to preserve different amounts for uppercase vs lowercase,
        # uncomment the following lines and adjust accordingly.
        # amount = '200' if args[0] == 'S' else '180'
        # For consistent behavior regardless of case:
        amount = '200'

        # --- Retrieve or generate TN code from MongoDB ---
        tn_entry = user_tn_codes_collection.find_one({'user_id': user_id})
        if tn_entry:
            unique_code = tn_entry['tn_code']
        else:
            unique_code = generate_unique_code()
            user_tn_codes_collection.insert_one({'user_id': user_id, 'tn_code': unique_code})

        qr_data = f'upi://pay?pa=Q682714937@ybl&pn=V-TECH&am={amount}&tn={unique_code}'

        # --- Retrieve or generate QR code from MongoDB ---
        qr_entry = qr_codes_collection.find_one({'tn_code': unique_code, 'amount': amount})
        if qr_entry:
            qr_image_data = qr_entry['qr_code_data']
        else:
            # Updated logo file ID (ensure this ID is valid)
            logo_file_id = "BQACAgUAAxkBAAOFZuXv8SPbZelS-gE53dNnyPZxxoEAAv8OAAKAe1lWvt2DsZHCldQ2BA"
            qr_image = generate_qr_code(qr_data, logo_file_id=logo_file_id)
            qr_stream = io.BytesIO()
            qr_image.save(qr_stream, format='PNG')
            qr_stream.seek(0)
            qr_image_data = qr_stream.getvalue()
            qr_codes_collection.insert_one({
                'tn_code': unique_code,
                'amount': amount,
                'qr_code_data': Binary(qr_image_data)
            })

        # --- Delete old messages asynchronously (do not await) ---
        context.application.create_task(delete_old_messages(user_id, context))

        # Updated messages to send list
        messages_to_send = [
            ("✨YOU PURCHASING✨", None, None),
            # This media file is assumed to be a photo.
            (None, 'AgACAgUAAxkBAAMDZuLGJEbWoqAogU2QF5yO45ByPwgAAim_MRukShlXvJeP2v8lCGEBAAMCAAN3AAM2BA', 
             "• 200₹ ~ Fᴜʟʟ Cᴏʟʟᴇᴄᴛɪᴏɴ 🥳\n• Qᴜɪᴄᴋ Dᴇʟɪᴇᴠᴇʀʏ Sʏsᴛᴇᴍ 🏎️💨\n• Nᴏ Lɪɴᴋ❗, Dɪʀᴇᴄᴛ 🍃\n• Oʀɢɪɴᴀʟ Qᴜᴀʟɪᴛʏ ☄️\n• Pʟᴜs Bᴏɴᴜs⚜"),
            ("🔱Qʀ ᴄᴏᴅᴇ ᴀɴᴅ ᴘᴀʏ Lɪɴᴋ👇", None, None),
            (None, qr_image_data, None),
            ("☄Qᴜɪᴄᴋ ᴘᴀʏ sʏsᴛᴇᴍ🎗", None, None),
            ("Tᴜᴛᴏʀɪᴀʟ : ʜᴏᴡ ᴛᴏ ᴘᴀʏ 👇", None, None),
            # This media file should be sent as a video.
            (None, "BAACAgUAAxkBAAJ5bWfcAAFscCgDEwLE_ZVKf-j-LYqoaQACQxgAAtjV6FIFkb7AFYpZxjYE", None),
        ]

        message_ids = []
        for text, content, caption in messages_to_send:
            try:
                # If content is None, just send a text message.
                if content is None:
                    message = await context.bot.send_message(chat_id=user_id, text=text)
                # If content is bytes, assume it's an image from QR generation.
                elif isinstance(content, bytes):
                    message = await context.bot.send_photo(chat_id=user_id, photo=io.BytesIO(content), caption=text)
                # If content is a string (file ID) check if it should be sent as video.
                elif isinstance(content, str):
                    if content in VIDEO_FILE_IDS:
                        # Send video; include caption if provided.
                        if caption:
                            message = await context.bot.send_video(chat_id=user_id, video=content, caption=caption)
                        else:
                            message = await context.bot.send_video(chat_id=user_id, video=content)
                    else:
                        # Send as photo; include caption if provided.
                        if caption:
                            message = await context.bot.send_photo(chat_id=user_id, photo=content, caption=caption)
                        else:
                            message = await context.bot.send_photo(chat_id=user_id, photo=content)
                else:
                    # Fallback to sending a text message if type is unknown.
                    message = await context.bot.send_message(chat_id=user_id, text=text)
                message_ids.append(message.message_id)
            except Exception as e:
                logging.error(f"Error sending message to user {user_id}: {e}")

        # --- Save user messages info to MongoDB ---
        user_messages_collection.insert_one({
            'user_id': user_id,
            'unique_code': unique_code,
            'amount': amount,
            'message_ids': message_ids
        })
    else:
        # New /start message when no parameters are provided.
        text = "Any help Contact: @XProvider\nor\n👇Sᴛᴀʀᴛ ғʀᴏᴍ ᴛʜɪs ʙᴏᴛ ᴛᴏ ʙᴜʏ"
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("IINKPROVIDER", url="https://t.me/Iinkprovider_bot")]
        ])
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=inline_keyboard
        )

async def delete_old_messages(user_id, context):
    # Retrieve and remove user's message document from MongoDB
    message_data = user_messages_collection.find_one_and_delete({'user_id': user_id})
    if message_data:
        for message_id in message_data.get('message_ids', []):
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=message_id)
                logging.info(f"Deleted message {message_id} for user {user_id}")
            except Exception as e:
                logging.error(f"Error deleting message {message_id} for user {user_id}: {e}")

# --- Admin deletion handlers ---

async def admin_delete_command(update: Update, context):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=user_id, text="You are not authorized to use this command.")
        return

    # Count pending messages by summing message_ids in all documents
    pending_messages = 0
    for doc in user_messages_collection.find():
        pending_messages += len(doc.get('message_ids', []))
    users_today = len(unique_users_today)
    users_total = len(unique_users_total)
    text = (
        f"Stats:\n"
        f"Users used today: {users_today}\n"
        f"Total users: {users_total}\n"
        f"Messages pending deletion: {pending_messages}\n\n"
        "Press the button below to delete all messages."
    )
    inline_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Confirm Delete All", callback_data="confirm_delete_all")]])
    await context.bot.send_message(chat_id=user_id, text=text, reply_markup=inline_keyboard)

async def confirm_delete_all_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    success_count = 0
    fail_count = 0
    # Iterate over all documents in user_messages_collection
    for doc in list(user_messages_collection.find()):
        uid = doc.get('user_id')
        for msg_id in doc.get('message_ids', []):
            try:
                await context.bot.delete_message(chat_id=uid, message_id=msg_id)
                success_count += 1
            except Exception as e:
                logging.error(f"Error deleting message {msg_id} for user {uid}: {e}")
                fail_count += 1
        # Remove the document after processing
        user_messages_collection.delete_one({'_id': doc['_id']})
    text = (
        f"Deletion completed.\n"
        f"Successfully deleted: {success_count} messages.\n"
        f"Failed to delete: {fail_count} messages."
    )
    await query.edit_message_text(text=text)

# --- Payment update handler ---
async def handle_payment_update(update: Update, context):
    try:
        message = update.channel_post.text
        if message.startswith('IT'):
            unique_code = message
            # Find the document with matching unique_code
            doc = user_messages_collection.find_one({'unique_code': unique_code})
            if doc:
                user_id = doc['user_id']
                # Send payment confirmation to the user
                await context.bot.send_message(chat_id=user_id, text="✨Payment Confirm✨")

                # Send the user ID to the specified inline button channel
                try:
                    button_text = "User ID"
                    button_url = f"tg://user?id={user_id}"
                    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=button_url)]])
                    await context.bot.send_message(
                        chat_id=INLINE_BUTTON_CHANNEL,
                        text=f"User ID: {user_id}",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logging.error(f"Error sending inline button to channel: {e}")
                    await context.bot.send_message(
                        chat_id=INLINE_BUTTON_CHANNEL,
                        text=f"User ID: {user_id}"
                    )

                # Also send a transaction message to the TR channel (CHANNEL_ID)
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=f"Transaction for User ID: {user_id}, TN Code: {unique_code}"
                )

                # Delete user's messages asynchronously
                context.application.create_task(delete_old_messages(user_id, context))

                # Send the updated video with caption to the user
                file_id = "BAACAgUAAxkBAAMHZuLGLkRq4Ej1PekdoULAdoyIeMUAAnEVAALsLxBXCdaESjhVUag2BA"
                caption = (
                    "⚡️𝐒𝐔𝐁𝐇𝐀𝐒𝐇𝐑𝐄𝐄 𝐒𝐀𝐇𝐔 𝐅𝐮𝐥𝐥 𝐂𝐨𝐥𝐥𝐞𝐜𝐭𝐢𝐨𝐧 𝐔𝐧𝐥𝐨𝐜𝐤𝐞𝐝 🔓\n\n"
                    "👇Sᴇɴᴅ A Mᴇssᴀɢᴇ Tᴏ Aᴅᴍɪɴ\n"
                    "t.me/iinkproviderr\n"
                    "t.me/iinkproviderr\n"
                    "t.me/iinkproviderr\n\n"
                    "Aᴅᴍɪɴ Sᴇɴᴅ Yᴏᴜ Dɪʀᴇᴄᴛʟʏ Aʟʟ Sᴜʙʜᴀ𝐒𝐇𝐑𝐄𝐄 𝐒𝐀𝐇𝐔 𝐂𝐨𝐥𝐥𝐞𝐜𝐭𝐢𝐨𝐧 😊\n\n"
                    "⚠️- if you can't send a message to admin then start this bot and send a message to admin at @iinkproviderrbot"
                )
                await context.bot.send_video(chat_id=user_id, video=file_id, caption=caption)

                # Create an inline button for contacting admin
                try:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("CONTACT: ADMIN", url="https://t.me/iinkproviderr")]
                    ])
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="click the button below to send message to admin. 📥𝗚𝗘𝗧 𝗖𝗢𝗟𝗟𝗘𝐶𝗧𝗜𝗢𝗡👇",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logging.error(f"Error sending admin contact button: {e}")
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="Contact admin at: https://t.me/iinkproviderr"
                    )
    except Exception as e:
        logging.error(f"Error handling payment update: {e}")

# --- Handler for all non-command messages ---
async def help_message(update: Update, context):
    if update.message:
        await context.bot.send_message(chat_id=update.message.chat_id, text="Any help Contact: @Xprocider")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete", admin_delete_command))
    # CallbackQuery Handler for admin deletion confirmation
    app.add_handler(CallbackQueryHandler(confirm_delete_all_callback, pattern="^confirm_delete_all$"))
    # Payment update handler for channel posts
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_payment_update))
    # Catch-all handler for any non-command message
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, help_message))

    app.run_polling()

if __name__ == '__main__':
    main()
