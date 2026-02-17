import os
import asyncio
import logging
import json
import hashlib
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CheckChatInviteRequest
import requests
import re

# إعداد تسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== الإعدادات ==========
logger.info("🔧 قراءة الإعدادات...")

API_ID = int(os.environ.get('API_ID', '0'))
API_HASH = os.environ.get('API_HASH', '')
SESSION = os.environ.get('SESSION_STRING', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
CHAT_ID_RAW = os.environ.get('CHAT_ID', '')
CHANNELS_INPUT = os.environ.get('CHANNELS', '')

# تنظيف CHAT_ID
CHAT_ID = CHAT_ID_RAW.strip() if CHAT_ID_RAW else ''

logger.info(f"API_ID: {'✅' if API_ID else '❌'}")
logger.info(f"API_HASH: {'✅' if API_HASH else '❌'} ({len(API_HASH)} حرف)")
logger.info(f"SESSION: {'✅' if SESSION else '❌'} ({len(SESSION)} حرف)")
logger.info(f"BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'} ({len(BOT_TOKEN)} حرف)")
logger.info(f"CHAT_ID: {'✅' if CHAT_ID else '❌'} (طول: {len(CHAT_ID)})")
logger.info(f"CHANNELS: {CHANNELS_INPUT[:50] if CHANNELS_INPUT else '❌'}...")

CHANNELS = [c.strip() for c in CHANNELS_INPUT.split(',') if c.strip()] if CHANNELS_INPUT else []
logger.info(f"عدد القنوات: {len(CHANNELS)}")

# AliExpress
ALI_APP_KEY = os.environ.get('ALI_APP_KEY', '')
ALI_TRACKING_ID = os.environ.get('ALI_TRACKING_ID', 'default')

DB_FILE = 'sent_links.json'

def load_sent_links():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في قراءة قاعدة البيانات: {e}")
            return []
    return []

def save_sent_links(links):
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(links, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 تم حفظ {len(links)} رابط")
    except Exception as e:
        logger.error(f"خطأ في الحفظ: {e}")

def send_telegram(message):
    """إرسال رسالة مع تسجيل كامل"""
    logger.info(f"📤 === بدء الإرسال ===")
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN غير موجود!")
        return False
    
    if not CHAT_ID:
        logger.error("❌ CHAT_ID غير موجود!")
        return False
    
    # التأكد من أن CHAT_ID رقم
    try:
        chat_id_int = int(CHAT_ID)
        logger.info(f"📤 Chat ID رقمي: {chat_id_int}")
    except ValueError:
        logger.error(f"❌ CHAT_ID ليس رقماً: '{CHAT_ID}'")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        'chat_id': chat_id_int,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    
    logger.info(f"📤 URL: {url[:50]}...")
    logger.info(f"📤 Chat ID: {chat_id_int}")
    logger.info(f"📤 الرسالة: {message[:80]}...")
    
    try:
        logger.info("📤 إرسال الطلب...")
        response = requests.post(url, json=payload, timeout=20)
        
        logger.info(f"📤 رد HTTP: {response.status_code}")
        logger.info(f"📤 نص الرد: {response.text[:300]}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                logger.info("✅ === تم الإرسال بنجاح! ===")
                return True
            else:
                logger.error(f"❌ Telegram رفض: {data.get('description')}")
                return False
        else:
            logger.error(f"❌ HTTP خطأ: {response.status_code}")
            logger.error(f"❌ الرد: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ انتهى وقت الانتظار!")
        return False
    except Exception as e:
        logger.error(f"❌ استثناء: {e}")
        return False

def test_bot():
    """اختبار البوت"""
    logger.info("🧪 === اختبار البوت ===")
    
    if not BOT_TOKEN:
        logger.error("❌ لا يوجد BOT_TOKEN")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    
    try:
        logger.info(f"🧪 طلب: {url[:50]}...")
        response = requests.get(url, timeout=10)
        logger.info(f"🧪 رد: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_name = data['result'].get('username', 'unknown')
                logger.info(f"✅ البوت يعمل: @{bot_name}")
                return True
        
        logger.error(f"❌ البوت لا يستجيب: {response.text[:200]}")
        return False
        
    except Exception as e:
        logger.error(f"❌ خطأ في اختبار البوت: {e}")
        return False

def is_aliexpress(url):
    return 'aliexpress' in url.lower()

def add_affiliate(url):
    """إضافة معلمات أفلييت بسيطة"""
    if not ALI_APP_KEY:
        return None
    
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        params['aff_fcid'] = [f'{ALI_APP_KEY}::{ALI_TRACKING_ID}']
        params['aff_platform'] = ['default']
        
        new_query = urlencode(params, doseq=True)
        new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        
        return new_url
    except:
        return None

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
        logger.error(f"فشل في {ch}: {e}")
        return None

async def main():
    logger.info("=" * 60)
    logger.info("🚀 بدء العملية")
    logger.info("=" * 60)
    
    # التحقق
    if not all([API_ID, API_HASH, SESSION, BOT_TOKEN, CHAT_ID]):
        logger.error("❌ إعدادات ناقصة!")
        logger.error(f"   API_ID={bool(API_ID)}, API_HASH={bool(API_HASH)}")
        logger.error(f"   SESSION={bool(SESSION)}, BOT_TOKEN={bool(BOT_TOKEN)}")
        logger.error(f"   CHAT_ID={bool(CHAT_ID)}")
        return
    
    if not CHANNELS:
        logger.error("❌ لا توجد قنوات!")
        return
    
    # اختبار البوت
    if not test_bot():
        logger.error("❌ فشل اختبار البوت")
        return
    
    # إرسال اختبار
    logger.info("🧪 === إرسال رسالة اختبار ===")
    test_result = send_telegram("✅ <b>البوت يعمل!</b>\nبدء الجمع...")
    
    if not test_result:
        logger.error("❌ فشل إرسال الاختبار! توقف.")
        return
    
    logger.info("✅ === الاختبار نجح، أكمل ===")
    
    # الجمع
    sent_links = load_sent_links()
    logger.info(f"📚 روابط محفوظة: {len(sent_links)}")
    
    all_items = []
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"👤 متصل: {me.first_name}")
        
        # تأكيد للمستخدم
        send_telegram(f"👤 <b>متصل كـ:</b> {me.first_name}\n📡 <b>القنوات:</b> {len(CHANNELS)}")
        
        for idx, ch in enumerate(CHANNELS, 1):
            logger.info(f"\n📡 [{idx}/{len(CHANNELS)}] {ch}")
            
            channel = await resolve_channel(client, ch)
            if not channel:
                send_telegram(f"❌ فشل الاتصال بـ: <code>{ch}</code>")
                continue
            
            send_telegram(f"✅ <b>{channel.title}</b> - جاري الجمع...")
            
            count = 0
            async for msg in client.iter_messages(channel, limit=30):
                if not msg.message:
                    continue
                
                urls = re.findall(r'https?://\S+', msg.message)
                
                for url in urls:
                    url = url.rstrip('.,;:!?)]}>"\'')
                    
                    if url in sent_links:
                        continue
                    
                    item = {
                        'url': url,
                        'channel': channel.title,
                        'text': msg.message[:80],
                        'is_ali': is_aliexpress(url),
                        'aff_url': None
                    }
                    
                    if item['is_ali']:
                        aff = add_affiliate(url)
                        if aff:
                            item['aff_url'] = aff
                    
                    all_items.append(item)
                    sent_links.append(url)
                    count += 1
            
            send_telegram(f"📊 <b>{channel.title}:</b> {count} روابط")
            await asyncio.sleep(2)
    
    # إرسال النتائج
    logger.info(f"\n📊 المجموع: {len(all_items)}")
    
    if all_items:
        save_sent_links(sent_links)
        
        ali_count = len([i for i in all_items if i['is_ali']])
        aff_count = len([i for i in all_items if i.get('aff_url')])
        
        # إرسال الروابط
        for item in all_items[:15]:
            if item.get('aff_url'):
                display = item['aff_url']
                badge = "💰 أفلييت"
            elif item['is_ali']:
                display = item['url']
                badge = "🛒 AliExpress"
            else:
                display = item['url']
                badge = "🔗"
            
            msg = f"{badge} | <b>{item['channel']}</b>\n\n"
            msg += f"<a href='{display}'>{display[:50]}...</a>\n\n"
            msg += f"📝 {item['text'][:60]}..."
            
            send_telegram(msg)
            await asyncio.sleep(0.5)
        
        # ملخص
        summary = f"📊 <b>انتهى</b>\n\n🛒 AliExpress: {ali_count}\n💰 بأفلييت: {aff_count}\n🔗 المجموع: {len(all_items)}"
        send_telegram(summary)
        
    else:
        send_telegram("📭 لا توجد روابط جديدة")
    
    logger.info("✅ انتهى البرنامج")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        import traceback
        logger.error(traceback.format_exc())
