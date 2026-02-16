import os
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
import requests
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# الإعدادات من Secrets
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
SESSION = os.environ['SESSION_STRING']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID = os.environ['CHAT_ID']
CHANNEL = os.environ['CHANNEL']

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'HTML'})

async def main():
    logger.info("🔌 جاري الاتصال...")
    
    # الاتصال بالجلسة المحفوظة
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"✅ متصل كـ: {me.first_name}")
        
        # الاتصال بالقناة
        try:
            channel = await client.get_entity(CHANNEL)
        except:
            # محاولة بدون @
            channel = await client.get_entity('@' + CHANNEL.replace('@', ''))
        
        logger.info(f"📡 قناة: {channel.title}")
        
        # جمع الروابط
        links = []
        async for msg in client.iter_messages(channel, limit=50):
            if msg.message:
                urls = re.findall(r'https?://\S+', msg.message)
                for url in urls:
                    if url not in [l['url'] for l in links]:
                        links.append({'url': url, 'text': msg.message[:50]})
        
        # إرسال النتائج
        if links:
            message = f"🔗 <b>{len(links)} روابط من {channel.title}</b>\n\n"
            for i, l in enumerate(links[:15], 1):
                message += f"{i}. <a href='{l['url']}'>{l['url'][:40]}</a>\n"
            send(message)
            logger.info(f"📤 أرسلت {len(links)} رابط")
        else:
            logger.info("📭 لا توجد روابط")

asyncio.run(main())
