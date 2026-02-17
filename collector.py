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

def send_telegram(message, photo_url=None):
    """إرسال رسالة نصية أو صورة"""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    
    try:
        chat_id = int(CHAT_ID)
    except:
        logger.error(f"CHAT_ID غير صالح: {CHAT_ID}")
        return False
    
    # إذا كان هناك رابط صورة، أرسل صورة
    if photo_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            'chat_id': chat_id,
            'photo': photo_url,
            'caption': message[:1024],  # Telegram limit
            'parse_mode': 'HTML'
        }
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False  # ← إظهار معاينة الرابط
        }
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200 and response.json().get('ok'):
            logger.info("✅ تم الإرسال")
            return True
        else:
            logger.error(f"❌ فشل: {response.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        return False

def extract_product_info(text):
    """استخراج معلومات المنتج من النص"""
    info = {
        'title': '',
        'price': '',
        'currency': '',
        'original_price': '',
        'discount': '',
        'emoji_flags': [],
        'description': text[:200] if text else ''
    }
    
    # استخراج السعر: 5.69$ أو 4.82€ أو 500 DA
    price_patterns = [
        r'السعر\s*[:：]?\s*(\d+[.,]?\d*)\s*(\$|€|£|DA|دينار|درهم)',
        r'(\d+[.,]?\d*)\s*(\$|€|£|DA)\s*🔥',
        r'(\d+[.,]?\d*)\s*(\$|€|£)',
        r'price\s*[:：]?\s*(\d+[.,]?\d*)\s*(\$|€|£)'
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info['price'] = match.group(1)
            info['currency'] = match.group(2)
            break
    
    # استخراج الخصم: 50% off أو تخفيض 50%
    discount_patterns = [
        r'تخفيض\s*(?:لـ)?\s*(\d+)%',
        r'خصم\s*(\d+)%',
        r'(\d+)%\s*off',
        r'save\s*(\d+)%'
    ]
    
    for pattern in discount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info['discount'] = match.group(1) + '%'
            break
    
    # استخراج العلامات الوطنية 🇩🇿 🇸🇦 🇲🇦
    flags = re.findall(r'[\U0001F1E0-\U0001F1FF]{2}', text)
    info['emoji_flags'] = flags
    
    # استخراج العنوان (السطر الأول عادة)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if lines:
        # تجاهل السطور التي تحتوي على روابط أو أسعار فقط
        for line in lines[:3]:
            if not any(x in line.lower() for x in ['http', 'سعر', 'price', '$', '€']):
                info['title'] = line[:100]
                break
    
    if not info['title'] and lines:
        info['title'] = lines[0][:100]
    
    return info

def is_aliexpress(url):
    return 'aliexpress' in url.lower() or 's.click.aliexpress' in url.lower()

def add_affiliate(url):
    """إضافة معلمات الأفلييت"""
    if not ALI_APP_KEY:
        return url  # ← إرجاع الرابط الأصلي إذا لا يوجد API
    
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # إضافة أو استبدال معلمات الأفلييت
        params['aff_fcid'] = [f'{ALI_APP_KEY}::{ALI_TRACKING_ID}']
        params['aff_platform'] = ['default']
        params['terminal_id'] = ['telegram_bot']
        
        new_query = urlencode(params, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except:
        return url

def get_photo_from_message(msg):
    """الحصول على رابط الصورة من الرسالة"""
    if msg.media:
        try:
            # إذا كانت الرسالة تحتوي على صورة
            if hasattr(msg.media, 'photo'):
                # سنعيد استخدام الرابط لاحقاً عبر Telethon
                return True  # علامة أن هناك صورة
        except:
            pass
    return False

async def resolve_channel(client, ch):
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
        logger.error(f"فشل {ch}: {e}")
        return None

async def main():
    logger.info("🚀 بدء العملية")
    
    if not all([API_ID, API_HASH, SESSION, BOT_TOKEN, CHAT_ID]):
        logger.error("❌ إعدادات ناقصة")
        return
    
    if not CHANNELS:
        logger.error("❌ لا توجد قنوات")
        return
    
    sent_links = load_sent_links()
    logger.info(f"📚 روابط محفوظة: {len(sent_links)}")
    
    all_items = []
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"👤 متصل: {me.first_name}")
        
        send_telegram(f"👤 <b>بدء الجمع:</b> {me.first_name}\n📡 {len(CHANNELS)} قنوات")
        
        for idx, ch in enumerate(CHANNELS, 1):
            logger.info(f"\n📡 [{idx}/{len(CHANNELS)}] {ch}")
            
            channel = await resolve_channel(client, ch)
            if not channel:
                send_telegram(f"❌ فشل: {ch}")
                continue
            
            send_telegram(f"✅ <b>{channel.title}</b>")
            
            count = 0
            
            async for msg in client.iter_messages(channel, limit=50):
                if not msg.message:
                    continue
                
                text = msg.message
                
                # البحث عن روابط AliExpress
                urls = re.findall(r'https?://(?:s\.click\.)?aliexpress\.com/\S+', text)
                
                for url in urls:
                    url = url.rstrip('.,;:!?)]}>"\'')
                    
                    if url in sent_links:
                        continue
                    
                    # استخراج المعلومات
                    info = extract_product_info(text)
                    has_photo = get_photo_from_message(msg)
                    
                    # تحويل الرابط
                    aff_url = add_affiliate(url)
                    
                    item = {
                        'url': url,
                        'aff_url': aff_url,
                        'channel': channel.title,
                        'title': info['title'],
                        'price': info['price'],
                        'currency': info['currency'],
                        'discount': info['discount'],
                        'flags': info['emoji_flags'],
                        'description': info['description'],
                        'has_photo': has_photo,
                        'date': str(msg.date)[:16] if msg.date else ''
                    }
                    
                    all_items.append(item)
                    sent_links.append(url)
                    count += 1
                    
                    logger.info(f"🛒 {info['title'][:50]} - {info['price']}{info['currency']}")
            
            send_telegram(f"📊 <b>{channel.title}:</b> {count} منتجات")
            await asyncio.sleep(2)
    
    # إرسال النتائج
    logger.info(f"\n📊 المجموع: {len(all_items)}")
    
    if all_items:
        save_sent_links(sent_links)
        
        # إرسال كل منتج
        for idx, item in enumerate(all_items[:20], 1):  # أول 20 فقط
            # بناء الرسالة بشكل جميل
            msg = ""
            
            # العلم
            if item['flags']:
                msg += " ".join(item['flags']) + "\n"
            
            # الخصم إذا موجود
            if item['discount']:
                msg += f"🏷️ <b>خصم {item['discount']}</b>\n"
            
            # العنوان
            if item['title']:
                msg += f"📦 <b>{item['title']}</b>\n\n"
            
            # السعر
            if item['price'] and item['currency']:
                msg += f"💰 <b>السعر:</b> {item['price']}{item['currency']} 🔥\n"
            
            # الرابط (مختصر)
            msg += f"\n🔗 <a href='{item['aff_url']}'>اضغط للشراء ⬅️</a>\n"
            
            # المصدر
            msg += f"\n📍 <i>{item['channel']}</i>"
            
            # إرسال
            send_telegram(msg)
            await asyncio.sleep(0.5)
        
        # ملخص
        with_aff = len([i for i in all_items if i['aff_url'] != i['url']])
        summary = f"📊 <b>انتهى!</b>\n\n"
        summary += f"🛒 منتجات: {len(all_items)}\n"
        summary += f"💰 بعمولة: {with_aff}\n"
        summary += f"📚 إجمالي محفوظ: {len(sent_links)}"
        send_telegram(summary)
        
    else:
        send_telegram("📭 لا توجد منتجات جديدة")
    
    logger.info("✅ انتهى")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        import traceback
        logger.error(traceback.format_exc())
