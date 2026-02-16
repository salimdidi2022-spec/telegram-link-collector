import os
import asyncio
import logging
import json
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
import requests
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# الإعدادات
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
SESSION = os.environ['SESSION_STRING']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID = os.environ['CHAT_ID']
CHANNEL = os.environ['CHANNEL']

# ملف حفظ الروابط المرسلة
DB_FILE = 'sent_links.json'

def load_sent_links():
    """تحميل الروابط المرسلة سابقاً"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return []

def save_sent_links(links):
    """حفظ الروابط المرسلة"""
    with open(DB_FILE, 'w') as f:
        json.dump(links, f)

def send(msg):
    """إرسال رسالة تلجرام"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            'chat_id': CHAT_ID, 
            'text': msg, 
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }, timeout=10)
    except Exception as e:
        logger.error(f"خطأ في الإرسال: {e}")

async def main():
    logger.info("🔌 جاري الاتصال...")
    
    # تحميل الروابط المرسلة سابقاً
    sent_links = load_sent_links()
    logger.info(f"📚 الروابط المحفوظة سابقاً: {len(sent_links)}")
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"✅ متصل كـ: {me.first_name}")
        
        # الاتصال بالقناة
        try:
            channel = await client.get_entity(CHANNEL)
        except:
            channel = await client.get_entity('@' + CHANNEL.replace('@', ''))
        
        logger.info(f"📡 قناة: {channel.title}")
        
        # جمع الروابط الجديدة فقط
        new_links = []
        
        async for msg in client.iter_messages(channel, limit=100):
            if msg.message:
                urls = re.findall(r'https?://\S+', msg.message)
                
                for url in urls:
                    # تنظيف الرابط
                    url = url.rstrip('.,;:!?)]}')
                    
                    # التحقق: هل الرابط جديد؟
                    if url not in sent_links:
                        new_links.append({
                            'url': url,
                            'text': msg.message[:80] if msg.message else '',
                            'date': str(msg.date)[:16] if msg.date else ''
                        })
                        sent_links.append(url)  # أضف للقائمة المحفوظة
        
        # إرسال النتائج
        if new_links:
            # حفظ الروابط الجديدة
            save_sent_links(sent_links)
            
            # إرسال على دفعات (كل 10 روابط)
            for i in range(0, len(new_links), 10):
                batch = new_links[i:i+10]
                
                message = f"🆕 <b>{len(new_links)} رابط جديد من {channel.title}</b>\n\n"
                
                for idx, link in enumerate(batch, i+1):
                    preview = link['text'][:50] + "..." if len(link['text']) > 50 else link['text']
                    message += f"{idx}. <a href='{link['url']}'>{link['url'][:45]}...</a>\n"
                    message += f"   📝 {preview}\n"
                    message += f"   📅 {link['date']}\n\n"
                
                send(message)
                await asyncio.sleep(1)
            
            logger.info(f"📤 أرسلت {len(new_links)} رابط جديد")
            
        else:
            logger.info("📭 لا توجد روابط جديدة")
            # إرسال رسالة كل 10 دقائق فقط للتأكد من أن البوت يعمل
            # (اختياري - يمكن إزالته)
            # send("✅ فحص دوري: لا توجد روابط جديدة")

asyncio.run(main())
