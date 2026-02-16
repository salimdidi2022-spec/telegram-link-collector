import os
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
import requests
import json
from datetime import datetime

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# جلب الإعدادات من المتغيرات
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
PHONE = os.environ.get('PHONE', '')
BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID = os.environ['CHAT_ID']
CHANNEL = os.environ['CHANNEL']  # مثال: @channel_name

# ملف الجلسة
SESSION_FILE = 'session.txt'

def send_telegram(message):
    """إرسال رسالة عبر البوت"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"خطأ في الإرسال: {e}")

def save_session(session_string):
    """حفظ الجلسة"""
    with open(SESSION_FILE, 'w') as f:
        f.write(session_string)

def load_session():
    """تحميل الجلسة"""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            return f.read().strip()
    return None

async def main():
    # تحميل الجلسة السابقة إن وجدت
    session_str = load_session()
    
    async with TelegramClient(
        StringSession(session_str), 
        API_ID, 
        API_HASH
    ) as client:
        
        # تسجيل الدخول في أول مرة
        if not session_str:
            logger.info("تسجيل الدخول لأول مرة...")
            await client.start(phone=PHONE)
            new_session = client.session.save()
            save_session(new_session)
            logger.info(f"تم حفظ الجلسة: {new_session[:20]}...")
            send_telegram("✅ تم تسجيل الدخول بنجاح!")
        
        # الاتصال بالقناة
        try:
            channel = await client.get_entity(CHANNEL)
            logger.info(f"متصل بـ: {channel.title}")
        except Exception as e:
            logger.error(f"خطأ في الاتصال بالقناة: {e}")
            send_telegram(f"❌ خطأ: لا يمكن الوصول للقناة {CHANNEL}")
            return
        
        # جمع آخر 20 رسالة
        new_links = []
        
        async for message in client.iter_messages(channel, limit=20):
            if message.message:
                # البحث عن روابط
                import re
                urls = re.findall(r'http[s]?://\S+', message.message)
                
                for url in urls:
                    # هنا يمكنك إضافة فحص قاعدة البيانات لتجنب التكرار
                    new_links.append({
                        'url': url,
                        'text': message.message[:100] + '...' if len(message.message) > 100 else message.message,
                        'date': str(message.date)
                    })
        
        # إرسال النتائج
        if new_links:
            msg = f"🔗 <b>تم العثور على {len(new_links)} رابط:</b>\n\n"
            for i, link in enumerate(new_links[:10], 1):  # أول 10 روابط فقط
                msg += f"{i}. <a href='{link['url']}'>{link['url'][:50]}...</a>\n"
                msg += f"📝 {link['text']}\n"
                msg += f"📅 {link['date']}\n\n"
            
            send_telegram(msg)
            logger.info(f"تم إرسال {len(new_links)} رابط")
        else:
            logger.info("لا توجد روابط جديدة")

if __name__ == '__main__':
    asyncio.run(main())
