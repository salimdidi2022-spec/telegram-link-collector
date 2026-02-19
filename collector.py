import os
import asyncio
import logging
import json
import re
import base64
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CheckChatInviteRequest
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== الإعدادات ==========
API_ID = int(os.environ.get('API_ID', '0'))
API_HASH = os.environ.get('API_HASH', '')
SESSION = os.environ.get('SESSION_STRING', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
CHAT_ID = os.environ.get('CHAT_ID', '').strip()
CHANNELS_INPUT = os.environ.get('CHANNELS', '')
CHANNELS = [c.strip() for c in CHANNELS_INPUT.split(',') if c.strip()] if CHANNELS_INPUT else []

ALI_APP_KEY = os.environ.get('ALI_APP_KEY', '')
ALI_TRACKING_ID = os.environ.get('ALI_TRACKING_ID', 'default')

DB_FILE = 'sent_links.json'
PHOTO_DIR = 'photos'

# إنشاء مجلد الصور
os.makedirs(PHOTO_DIR, exist_ok=True)

def load_sent_links():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_sent_links(links):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, indent=2)

def send_telegram_message(text, photo_path=None):
    """إرسال رسالة نصية أو مع صورة"""
    if not BOT_TOKEN or not CHAT_ID:
        logger.error("❌ BOT_TOKEN أو CHAT_ID غير موجود")
        return False
    
    try:
        chat_id = int(CHAT_ID)
    except:
        logger.error(f"❌ CHAT_ID غير صالح: {CHAT_ID}")
        return False
    
    url_base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    
    try:
        if photo_path and os.path.exists(photo_path):
            # إرسال مع صورة
            logger.info(f"📤 إرسال صورة: {photo_path}")
            url = f"{url_base}/sendPhoto"
            
            with open(photo_path, 'rb') as photo_file:
                files = {'photo': photo_file}
                data = {
                    'chat_id': chat_id,
                    'caption': text[:1024],
                    'parse_mode': 'HTML'
                }
                response = requests.post(url, files=files, data=data, timeout=30)
        else:
            # إرسال نص فقط
            logger.info(f"📤 إرسال نص: {text[:60]}...")
            url = f"{url_base}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            response = requests.post(url, json=payload, timeout=20)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                logger.info("✅ تم الإرسال بنجاح")
                return True
            else:
                logger.error(f"❌ Telegram API رفض: {result}")
                return False
        else:
            logger.error(f"❌ HTTP {response.status_code}: {response.text[:200]}")
            return False
            
    except Exception as e:
        logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

def is_aliexpress_url(url):
    if not url:
        return False
    url_lower = url.lower()
    return any(x in url_lower for x in ['aliexpress.com', 's.click.aliexpress', 'a.aliexpress'])

def extract_aliexpress_urls(text):
    """استخراج روابط AliExpress فقط"""
    if not text:
        return []
    pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(pattern, text)
    ali_urls = []
    for url in urls:
        url = url.rstrip('.,;:!?)]}>"\'')
        if is_aliexpress_url(url):
            ali_urls.append(url)
    return ali_urls

def convert_to_affiliate(url):
    """تحويل الرابط إلى أفلييت"""
    if not ALI_APP_KEY or not is_aliexpress_url(url):
        return url
    
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        params['aff_fcid'] = [f'{ALI_APP_KEY}::{ALI_TRACKING_ID}']
        params['aff_platform'] = ['default']
        params['terminal_id'] = ['telegram_bot']
        
        new_query = urlencode(params, doseq=True)
        new_url = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, new_query, parsed.fragment
        ))
        
        logger.info(f"🔄 تحويل: {url[:50]}... → {new_url[:50]}...")
        return new_url
        
    except Exception as e:
        logger.error(f"❌ خطأ في التحويل: {e}")
        return url

def replace_urls_in_text(text, old_url, new_url):
    """استبدال رابط واحد في النص"""
    return text.replace(old_url, new_url)

async def download_photo(client, msg, filename):
    """تحميل الصورة من الرسالة"""
    try:
        if not msg.photo:
            logger.info("ℹ️ لا توجد صورة في الرسالة")
            return None
        
        path = os.path.join(PHOTO_DIR, filename)
        
        # تحميل الصورة
        logger.info(f"📥 تحميل صورة إلى: {path}")
        downloaded_path = await client.download_media(msg.photo, file=path)
        
        if downloaded_path and os.path.exists(downloaded_path):
            logger.info(f"✅ تم تحميل الصورة: {downloaded_path}")
            return downloaded_path
        else:
            logger.error("❌ فشل تحميل الصورة")
            return None
            
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل الصورة: {e}")
        return None

async def resolve_channel(client, ch):
    """حل معرف القناة"""
    try:
        if ch.startswith('@'):
            return await client.get_entity(ch)
        if 't.me/' in ch:
            path = urlparse(ch).path.strip('/')
            if path.startswith('+'):
                r = await client(CheckChatInviteRequest(path[1:]))
                return r.chat if hasattr(r, 'chat') else None
            return await client.get_entity('@' + path)
        return await client.get_entity('@' + ch)
    except Exception as e:
        logger.error(f"فشل في {ch}: {e}")
        return None

async def main():
    logger.info("=" * 60)
    logger.info("🚀 بدء النسخ مع الصور")
    logger.info("=" * 60)
    
    # التحقق من الإعدادات
    if not all([API_ID, API_HASH, SESSION, BOT_TOKEN, CHAT_ID]):
        logger.error("❌ إعدادات ناقصة!")
        return
    
    if not CHANNELS:
        logger.error("❌ لا توجد قنوات!")
        return
    
    logger.info(f"📡 {len(CHANNELS)} قنوات")
    logger.info(f"💰 AliExpress: {'مفعل' if ALI_APP_KEY else 'معطل'}")
    
    sent_links = load_sent_links()
    logger.info(f"📚 روابط محفوظة: {len(sent_links)}")
    
    processed = 0
    skipped = 0
    errors = 0
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"👤 متصل: {me.first_name}")
        
        send_telegram_message(f"👤 <b>بدء النسخ:</b> {me.first_name}\n📡 {len(CHANNELS)} قنوات")
        
        for idx, channel_input in enumerate(CHANNELS, 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"📡 [{idx}/{len(CHANNELS)}] {channel_input}")
            
            channel = await resolve_channel(client, channel_input)
            if not channel:
                logger.error(f"❌ فشل: {channel_input}")
                send_telegram_message(f"❌ فشل: <code>{channel_input}</code>")
                errors += 1
                continue
            
            logger.info(f"✅ متصل: {channel.title}")
            send_telegram_message(f"✅ <b>{channel.title}</b>")
            
            channel_count = 0
            
            try:
                async for msg in client.iter_messages(channel, limit=20):
                    if not msg.message:
                        continue
                    
                    original_text = msg.message
                    
                    # البحث عن روابط AliExpress
                    ali_urls = extract_aliexpress_urls(original_text)
                    
                    if not ali_urls:
                        continue
                    
                    first_url = ali_urls[0]
                    
                    # التحقق من عدم التكرار
                    if first_url in sent_links:
                        skipped += 1
                        continue
                    
                    logger.info(f"📝 معالجة: {original_text[:60]}...")
                    
                    # تحويل الروابط
                    new_text = original_text
                    for old_url in ali_urls:
                        new_url = convert_to_affiliate(old_url)
                        new_text = replace_urls_in_text(new_text, old_url, new_url)
                    
                    # إضافة توقيع
                    if ALI_APP_KEY:
                        new_text += "\n\n💎 <i>رابط مخصص لك</i>"
                    
                    # تحميل الصورة إذا وجدت
                    photo_path = None
                    if msg.photo:
                        photo_filename = f"photo_{channel.id}_{msg.id}.jpg"
                        photo_path = await download_photo(client, msg, photo_filename)
                    
                    # إرسال الرسالة
                    logger.info(f"📤 إرسال...")
                    success = send_telegram_message(new_text, photo_path)
                    
                    if success:
                        logger.info("✅ تم الإرسال")
                        sent_links.append(first_url)
                        save_sent_links(sent_links)
                        processed += 1
                        channel_count += 1
                        
                        # حذف الصورة بعد الإرسال (توفير مساحة)
                        if photo_path and os.path.exists(photo_path):
                            try:
                                os.remove(photo_path)
                                logger.info(f"🗑️ حذف الصورة المؤقتة")
                            except:
                                pass
                    else:
                        logger.error("❌ فشل الإرسال")
                        errors += 1
                    
                    await asyncio.sleep(2)  # تأخير أطول للصور
                
                logger.info(f"📊 {channel.title}: {channel_count}")
                send_telegram_message(f"📊 <b>{channel.title}:</b> {channel_count} منشورات")
                
            except Exception as e:
                logger.error(f"❌ خطأ: {e}")
                send_telegram_message(f"⚠️ خطأ في {channel.title}")
                errors += 1
            
            await asyncio.sleep(3)
    
    # ملخص
    logger.info(f"\n{'='*50}")
    logger.info(f"✅ منشورات: {processed}")
    logger.info(f"⏭️ مكررة: {skipped}")
    logger.info(f"❌ أخطاء: {errors}")
    
    summary = f"📊 <b>انتهى!</b>\n\n✅ منشورات: {processed}\n⏭️ مكررة: {skipped}\n❌ أخطاء: {errors}\n📚 محفوظ: {len(sent_links)}"
    send_telegram_message(summary)
    
    # تنظيف الصور المتبقية
    try:
        for f in os.listdir(PHOTO_DIR):
            os.remove(os.path.join(PHOTO_DIR, f))
        logger.info("🧹 تم تنظيف الصور")
    except:
        pass

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        import traceback
        logger.error(traceback.format_exc())
