import os
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.types import PeerChannel
import requests
import re
from datetime import datetime
from urllib.parse import urlparse

# إعداد التسجيل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# الإعدادات
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
PHONE = os.environ.get('PHONE', '')
BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID = os.environ['CHAT_ID']
CHANNEL_INPUT = os.environ['CHANNEL']  # يمكن أن يكون @channel, t.me/+, أو ID

SESSION_FILE = 'session.txt'

def send_telegram(message):
    """إرسال رسالة عبر البوت"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("✅ تم إرسال الرسالة")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

def save_session(session_string):
    """حفظ الجلسة"""
    with open(SESSION_FILE, 'w') as f:
        f.write(session_string)
    logger.info("💾 تم حفظ الجلسة")

def load_session():
    """تحميل الجلسة"""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            return f.read().strip()
    return None

async def resolve_channel(client, channel_input):
    """
    تحويل أي شكل من أشكال الروابط إلى كيان قناة
    يدعم: @channel, t.me/channel, t.me/+, ID رقمي
    """
    channel_input = channel_input.strip()
    logger.info(f"🔍 محاولة الاتصال بـ: {channel_input}")
    
    # الحالة 1: معرف مباشر @channel_name
    if channel_input.startswith('@'):
        try:
            entity = await client.get_entity(channel_input)
            logger.info(f"✅ تم الاتصال بالقناة (معرف مباشر): {entity.title}")
            return entity
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بالمعرف المباشر: {e}")
            return None
    
    # الحالة 2: رابط t.me كامل
    if channel_input.startswith('https://t.me/') or channel_input.startswith('http://t.me/'):
        # استخراج الجزء الأخير من الرابط
        path = urlparse(channel_input).path.strip('/')
        
        # إذا كان رابط دعوة خاص (يبدأ بـ +)
        if path.startswith('+'):
            invite_hash = path[1:]  # إزالة +
            logger.info(f"🔑 محاولة الانضمام برابط دعوة: {invite_hash}")
            
            try:
                # محاولة الانضمام للقناة
                result = await client(CheckChatInviteRequest(invite_hash))
                
                if hasattr(result, 'chat'):
                    channel = result.chat
                    logger.info(f"✅ تم العثور على قناة بالدعوة: {channel.title}")
                    
                    # التحقق من الانضمام
                    try:
                        await client.get_participants(channel, limit=1)
                        logger.info("✅ تم التحقق من الانضمام للقناة")
                    except Exception as e:
                        logger.warning(f"⚠️ قد لا تكون منضماً للقناة: {e}")
                        send_telegram(f"⚠️ تنبيه: أنا لست عضواً في القناة {channel.title}!\nيرجى إضافتي للقناة أولاً.")
                    
                    return channel
                else:
                    logger.error("❌ لم يتم العثور على قناة في نتيجة الدعوة")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ خطأ في رابط الدعوة: {e}")
                # محاولة ثانية: ربما هو معرف عام بدون @
                if not channel_input.startswith('@'):
                    try:
                        entity = await client.get_entity('@' + path)
                        logger.info(f"✅ تم الاتصال كمعرف عام: {entity.title}")
                        return entity
                    except:
                        pass
                return None
        
        # إذا كان رابط عام t.me/channel_name
        else:
            try:
                entity = await client.get_entity('@' + path)
                logger.info(f"✅ تم الاتصال برابط عام: {entity.title}")
                return entity
            except Exception as e:
                logger.error(f"❌ فشل الاتصال برابط t.me: {e}")
                return None
    
    # الحالة 3: ID رقمي (Peer ID)
    if channel_input.lstrip('-').isdigit():
        try:
            channel_id = int(channel_input)
            # إذا كان ID داخلي (يحتاج إلى -100)
            if channel_id > 0:
                channel_id = int(f"-100{channel_id}")
            
            entity = await client.get_entity(PeerChannel(channel_id))
            logger.info(f"✅ تم الاتصال بـ ID رقمي: {entity.title}")
            return entity
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بـ ID رقمي: {e}")
            return None
    
    # الحالة 4: اسم بدون @
    try:
        entity = await client.get_entity('@' + channel_input)
        logger.info(f"✅ تم الاتصال بإضافة @ تلقائياً: {entity.title}")
        return entity
    except:
        pass
    
    logger.error(f"❌ لم يتم التعرف على الشكل: {channel_input}")
    return None

async def main():
    session_str = load_session()
    
    async with TelegramClient(
        StringSession(session_str), 
        API_ID, 
        API_HASH
    ) as client:
        
        # تسجيل الدخول في أول مرة
        if not session_str:
            logger.info("🔐 تسجيل الدخول لأول مرة...")
            await client.start(phone=PHONE)
            new_session = client.session.save()
            save_session(new_session)
            send_telegram("✅ تم تسجيل الدخول بنجاح!\nالجلسة محفوظة للتشغيلات القادمة.")
        
        # حل القناة من الإدخال
        channel = await resolve_channel(client, CHANNEL_INPUT)
        
        if not channel:
            error_msg = f"❌ لم يتم العثور على القناة: {CHANNEL_INPUT}\n\nالأشكال المدعومة:\n• @channel_name\n• https://t.me/channel_name\n• https://t.me/+invite_code\n• -1001234567890"
            logger.error(error_msg)
            send_telegram(error_msg)
            return
        
        # جمع الروابط
        logger.info(f"📥 جمع الروابط من: {channel.title}")
        links_found = []
        
        try:
            async for message in client.iter_messages(channel, limit=50):
                if message.message:
                    # البحث عن الروابط
                    urls = re.findall(r'http[s]?://[^\s<>\"{}|\\^`\[\]]+', message.message)
                    
                    for url in urls:
                        # تنظيف الرابط
                        url = url.rstrip('.,;:!?)]}')
                        
                        links_found.append({
                            'url': url,
                            'preview': message.message[:80].replace('\n', ' '),
                            'date': str(message.date)[:16] if message.date else 'unknown',
                            'msg_id': message.id
                        })
            
            # إزالة التكرار
            seen = set()
            unique_links = []
            for link in links_found:
                if link['url'] not in seen:
                    seen.add(link['url'])
                    unique_links.append(link)
            
            logger.info(f"📊 تم العثور على {len(unique_links)} رابط فريد")
            
            # إرسال النتائج
            if unique_links:
                # تقسيم إلى مجموعات إذا كانت كثيرة
                batch_size = 10
                for i in range(0, len(unique_links), batch_size):
                    batch = unique_links[i:i+batch_size]
                    
                    msg = f"🔗 <b>روابط جديدة ({i+1}-{min(i+len(batch), len(unique_links))} من {len(unique_links)})</b>\n"
                    msg += f"📢 من قناة: <i>{channel.title}</i>\n\n"
                    
                    for idx, link in enumerate(batch, i+1):
                        # تقصير النص للعرض
                        preview = link['preview']
                        if len(preview) > 60:
                            preview = preview[:60] + "..."
                        
                        msg += f"{idx}. <a href='{link['url']}'>{link['url'][:40]}...</a>\n"
                        msg += f"   📝 {preview}\n"
                        msg += f"   📅 {link['date']}\n\n"
                    
                    send_telegram(msg)
                    await asyncio.sleep(1)  # تأخير بين الرسائل
            
            else:
                logger.info("📭 لا توجد روابط في هذه الجولة")
                # إرسال رسالة كل 10 جولات فقط (للتأكد من أن البوت يعمل)
                # يمكنك إزالة هذا أو تعديله
                
        except Exception as e:
            error_msg = f"❌ خطأ أثناء جمع الرسائل: {str(e)}"
            logger.error(error_msg)
            send_telegram(error_msg)

if __name__ == '__main__':
    asyncio.run(main())
