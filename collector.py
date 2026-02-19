import os
import asyncio
import logging
import json
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.types import InputMediaPhotoExternal
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

def send_telegram_text(text, reply_to=None):
    """إرسال نص فقط"""
    if not BOT_TOKEN or not CHAT_ID:
        return None
    
    try:
        chat_id = int(CHAT_ID)
    except:
        return None
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False,
        'reply_to_message_id': reply_to
    }
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            return response.json()['result']['message_id']
        return None
    except:
        return None

def send_telegram_photo(photo_url, caption, reply_to=None):
    """إرسال صورة مع نص"""
    if not BOT_TOKEN or not CHAT_ID:
        return None
    
    try:
        chat_id = int(CHAT_ID)
    except:
        return None
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {
        'chat_id': chat_id,
        'photo': photo_url,
        'caption': caption[:1024],  # حد Telegram
        'parse_mode': 'HTML',
        'reply_to_message_id': reply_to
    }
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            return response.json()['result']['message_id']
        return None
    except:
        return None

def send_telegram_media_group(media, reply_to=None):
    """إرسال مجموعة صور"""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    
    try:
        chat_id = int(CHAT_ID)
    except:
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
    payload = {
        'chat_id': chat_id,
        'media': media,
        'reply_to_message_id': reply_to
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        return response.status_code == 200 and response.json().get('ok')
    except:
        return False

def is_aliexpress_url(url):
    """التحقق من رابط AliExpress"""
    if not url:
        return False
    url_lower = url.lower()
    patterns = [
        'aliexpress.com',
        's.click.aliexpress.com',
        'a.aliexpress.com',
        'www.aliexpress.com'
    ]
    return any(p in url_lower for p in patterns)

def extract_urls(text):
    """استخراج جميع الروابط من النص"""
    if not text:
        return []
    # نمط شامل للروابط
    pattern = r'https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    urls = re.findall(pattern, text)
    # تنظيف
    cleaned = []
    for url in urls:
        url = url.rstrip('.,;:!?)]}>"\'')
        if is_aliexpress_url(url):
            cleaned.append(url)
    return cleaned

def convert_to_affiliate(original_url):
    """تحويل الرابط إلى أفلييت"""
    if not ALI_APP_KEY or not is_aliexpress_url(original_url):
        return original_url
    
    try:
        parsed = urlparse(original_url)
        params = parse_qs(parsed.query)
        
        # إضافة/تحديث معلمات الأفلييت
        params['aff_fcid'] = [f'{ALI_APP_KEY}::{ALI_TRACKING_ID}']
        params['aff_platform'] = ['default']
        params['terminal_id'] = ['telegram_bot']
        params['aff_trace_key'] = [f'{ALI_TRACKING_ID}_{int(datetime.now().timestamp())}']
        
        # إعادة بناء الرابط
        new_query = urlencode(params, doseq=True)
        new_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        logger.info(f"🔄 تحويل: {original_url[:50]}... → {new_url[:50]}...")
        return new_url
        
    except Exception as e:
        logger.error(f"❌ خطأ في التحويل: {e}")
        return original_url

def replace_urls_in_text(text, url_mapping):
    """استبدال الروابط في النص"""
    if not text or not url_mapping:
        return text
    
    new_text = text
    for old_url, new_url in url_mapping.items():
        new_text = new_text.replace(old_url, new_url)
    
    return new_text

def get_message_photos(msg):
    """الحصول على روابط صور الرسالة"""
    photos = []
    
    try:
        # صورة واحدة
        if msg.photo:
            # الحصول على أعلى دقة
            photo = msg.photo
            if hasattr(photo, 'sizes') and photo.sizes:
                biggest = max(photo.sizes, key=lambda x: x.size if hasattr(x, 'size') else 0)
                photos.append(biggest)
            else:
                photos.append(photo)
        
        # ألبوم صور
        elif msg.grouped_id and msg.media:
            # سيتم معالجتها في الرسائل المجمعة
            pass
            
    except Exception as e:
        logger.error(f"خطأ في استخراج الصور: {e}")
    
    return photos

async def download_photo_url(client, photo):
    """تحميل الصورة والحصول على رابط مؤقت"""
    try:
        # تحميل الصورة إلى ملف مؤقت
        path = await client.download_media(photo, file='temp_photo.jpg')
        if path:
            # رفع الصورة للحصول على رابط
            # في GitHub Actions، نستخدم طريقة أخرى: إرسال مباشرة عبر البوت
            return path
    except Exception as e:
        logger.error(f"خطأ في تحميل الصورة: {e}")
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

async def process_message(client, msg, sent_links):
    """معالجة رسالة واحدة"""
    if not msg.message:
        return None
    
    original_text = msg.message
    logger.info(f"📝 معالجة رسالة: {original_text[:80]}...")
    
    # استخراج روابط AliExpress
    ali_urls = extract_urls(original_text)
    
    if not ali_urls:
        logger.info("ℹ️ لا يوجد رابط AliExpress في هذه الرسالة")
        return None
    
    # التحقق من عدم التكرار (باستخدام أول رابط)
    first_url = ali_urls[0]
    if first_url in sent_links:
        logger.info("⏭️ تم تجاوزها (مكررة)")
        return None
    
    # تحويل الروابط
    url_mapping = {}
    for url in ali_urls:
        new_url = convert_to_affiliate(url)
        url_mapping[url] = new_url
    
    # استبدال الروابط في النص
    new_text = replace_urls_in_text(original_text, url_mapping)
    
    # إضافة توقيع صغير (اختياري)
    if ALI_APP_KEY:
        new_text += f"\n\n💎 <i>رابط مخصص لك</i>"
    
    # الحصول على الصور
    photos = []
    try:
        if msg.photo:
            photos.append(msg.photo)
        elif msg.media and hasattr(msg.media, 'photo'):
            photos.append(msg.media.photo)
    except:
        pass
    
    return {
        'original_text': original_text,
        'new_text': new_text,
        'photos': photos,
        'urls_converted': len(url_mapping),
        'first_url': first_url
    }

async def send_message_with_photos(bot_token, chat_id, text, photos):
    """إرسال رسالة مع الصور باستخدام البوت"""
    if not photos:
        # نص فقط
        return send_telegram_text(text)
    
    # إذا كانت صورة واحدة
    if len(photos) == 1:
        try:
            # الحصول على رابط الصورة
            # في الوضع المبسط، نرسل النص مع معاينة الرابط
            return send_telegram_text(text)
        except:
            return send_telegram_text(text)
    
    # إذا كانت متعددة، نرسل النص فقط (الصور تحتاج إلى رفع)
    return send_telegram_text(text)

async def main():
    logger.info("=" * 60)
    logger.info("🚀 بدء نسخ المنشورات مع تحويل الروابط")
    logger.info("=" * 60)
    
    # التحقق من الإعدادات
    if not all([API_ID, API_HASH, SESSION, BOT_TOKEN, CHAT_ID]):
        logger.error("❌ إعدادات ناقصة!")
        logger.error(f"API_ID: {bool(API_ID)}, API_HASH: {bool(API_HASH)}")
        logger.error(f"SESSION: {bool(SESSION)}, BOT_TOKEN: {bool(BOT_TOKEN)}")
        logger.error(f"CHAT_ID: {bool(CHAT_ID)}")
        return
    
    if not CHANNELS:
        logger.error("❌ لا توجد قنوات!")
        return
    
    logger.info(f"📡 {len(CHANNELS)} قنوات: {CHANNELS}")
    logger.info(f"💰 AliExpress API: {'مفعل' if ALI_APP_KEY else 'غير مفعل'}")
    
    # تحميل الروابط المحفوظة
    sent_links = load_sent_links()
    logger.info(f"📚 روابط محفوظة سابقاً: {len(sent_links)}")
    
    processed_count = 0
    skipped_count = 0
    error_count = 0
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"👤 متصل كـ: {me.first_name} (@{me.username})")
        
        # إرسال رسالة بدء
        send_telegram_text(f"👤 <b>بدء النسخ:</b> {me.first_name}\n📡 {len(CHANNELS)} قنوات\n💰 الأفلييت: {'مفعل' if ALI_APP_KEY else 'معطل'}")
        
        # معالجة كل قناة
        for idx, channel_input in enumerate(CHANNELS, 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"📡 [{idx}/{len(CHANNELS)}] {channel_input}")
            logger.info(f"{'='*50}")
            
            # الاتصال بالقناة
            channel = await resolve_channel(client, channel_input)
            if not channel:
                logger.error(f"❌ فشل الاتصال بـ {channel_input}")
                send_telegram_text(f"❌ فشل الاتصال: <code>{channel_input}</code>")
                error_count += 1
                continue
            
            logger.info(f"✅ متصل بـ: {channel.title}")
            send_telegram_text(f"✅ <b>{channel.title}</b> - جاري النسخ...")
            
            channel_processed = 0
            
            # جمع الرسائل
            try:
                async for msg in client.iter_messages(channel, limit=30):
                    result = await process_message(client, msg, sent_links)
                    
                    if result is None:
                        skipped_count += 1
                        continue
                    
                    # إرسال المنشور
                    logger.info(f"📤 إرسال منشور مع {result['urls_converted']} رابط محول")
                    
                    # إرسال النص (مع الصورة إذا وجدت)
                    # ملاحظة: في GitHub Actions، نرسل النص فقط مع الروابط المحولة
                    # لأن الصور تحتاج إلى رفع ملفات
                    
                    send_result = send_telegram_text(result['new_text'])
                    
                    if send_result:
                        logger.info("✅ تم الإرسال بنجاح")
                        # حفظ الرابط
                        sent_links.append(result['first_url'])
                        save_sent_links(sent_links)
                        processed_count += 1
                        channel_processed += 1
                    else:
                        logger.error("❌ فشل الإرسال")
                        error_count += 1
                    
                    # تأخير بين المنشورات
                    await asyncio.sleep(1)
                
                logger.info(f"📊 {channel.title}: {channel_processed} منشور")
                send_telegram_text(f"📊 <b>{channel.title}</b>\nمنشورات: {channel_processed}")
                
            except Exception as e:
                logger.error(f"❌ خطأ في معالجة {channel.title}: {e}")
                send_telegram_text(f"⚠️ خطأ في {channel.title}: <code>{str(e)[:100]}</code>")
                error_count += 1
            
            # تأخير بين القنوات
            if idx < len(CHANNELS):
                await asyncio.sleep(3)
    
    # الملخص النهائي
    logger.info(f"\n{'='*50}")
    logger.info("📊 ملخص النهائي")
    logger.info(f"{'='*50}")
    logger.info(f"✅ منشورات منسوخة: {processed_count}")
    logger.info(f"⏭️ تم تجاوزها: {skipped_count}")
    logger.info(f"❌ أخطاء: {error_count}")
    logger.info(f"📚 إجمالي الروابط: {len(sent_links)}")
    
    summary = f"📊 <b>انتهى النسخ!</b>\n\n"
    summary += f"✅ منشورات: {processed_count}\n"
    summary += f"⏭️ مكررة: {skipped_count}\n"
    summary += f"❌ أخطاء: {error_count}\n"
    summary += f"📚 إجمالي محفوظ: {len(sent_links)}"
    
    send_telegram_text(summary)
    logger.info("✅ انتهى البرنامج بنجاح")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # محاولة إرسال تنبيه
        try:
            send_telegram_text(f"❌ <b>توقف البوت:</b>\n<code>{str(e)[:200]}</code>")
        except:
            pass
