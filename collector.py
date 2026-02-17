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

# إعداد تسجيل مفصل
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

CHAT_ID = CHAT_ID_RAW.strip() if CHAT_ID_RAW else ''

logger.info(f"API_ID: {'✅' if API_ID else '❌'}")
logger.info(f"API_HASH: {'✅' if API_HASH else '❌'}")
logger.info(f"SESSION: {'✅' if SESSION else '❌'} ({len(SESSION)} حرف)")
logger.info(f"BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
logger.info(f"CHAT_ID: {'✅' if CHAT_ID else '❌'} (طول: {len(CHAT_ID)})")
logger.info(f"CHANNELS: {CHANNELS_INPUT[:50]}...")

CHANNELS = [c.strip() for c in CHANNELS_INPUT.split(',') if c.strip()] if CHANNELS_INPUT else []
logger.info(f"عدد القنوات: {len(CHANNELS)}")

ALI_APP_KEY = os.environ.get('ALI_APP_KEY', '')
ALI_TRACKING_ID = os.environ.get('ALI_TRACKING_ID', 'default')

DB_FILE = 'sent_links.json'

def load_sent_links():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في قراءة DB: {e}")
            return []
    return []

def save_sent_links(links):
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(links, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 حفظ {len(links)} رابط")
    except Exception as e:
        logger.error(f"خطأ في الحفظ: {e}")

def send_telegram(message):
    """إرسال رسالة"""
    if not BOT_TOKEN or not CHAT_ID:
        logger.error("❌ BOT_TOKEN أو CHAT_ID ناقص!")
        return False
    
    try:
        chat_id_int = int(CHAT_ID)
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
    
    logger.info(f"📤 إرسال لـ {chat_id_int}: {message[:60]}...")
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        logger.info(f"📤 رد HTTP: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                logger.info("✅ تم الإرسال!")
                return True
            else:
                logger.error(f"❌ Telegram رفض: {data}")
                return False
        else:
            logger.error(f"❌ HTTP {response.status_code}: {response.text[:200]}")
            return False
            
    except Exception as e:
        logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

def test_bot():
    """اختبار البوت"""
    if not BOT_TOKEN:
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                logger.info(f"✅ البوت: @{data['result']['username']}")
                return True
        return False
    except Exception as e:
        logger.error(f"❌ خطأ في اختبار البوت: {e}")
        return False

def is_aliexpress(url):
    return 'aliexpress' in url.lower()

def add_affiliate(url):
    """إضافة أفلييت"""
    if not ALI_APP_KEY:
        return None
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params['aff_fcid'] = [f'{ALI_APP_KEY}::{ALI_TRACKING_ID}']
        params['aff_platform'] = ['default']
        new_query = urlencode(params, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except:
        return None

async def resolve_channel(client, ch):
    """حل القناة"""
    try:
        logger.info(f"🔍 حل: {ch}")
        
        if ch.startswith('@'):
            entity = await client.get_entity(ch)
            logger.info(f"✅ @ تم: {entity.title}")
            return entity
        
        if 't.me/' in ch:
            path = urlparse(ch).path.strip('/')
            if path.startswith('+'):
                logger.info(f"🔑 دعوة: {path[:10]}...")
                r = await client(CheckChatInviteRequest(path[1:]))
                if hasattr(r, 'chat'):
                    logger.info(f"✅ دعوة تم: {r.chat.title}")
                    return r.chat
                return None
            entity = await client.get_entity('@' + path)
            logger.info(f"✅ t.me تم: {entity.title}")
            return entity
        
        entity = await client.get_entity('@' + ch)
        logger.info(f"✅ بدون @ تم: {entity.title}")
        return entity
        
    except Exception as e:
        logger.error(f"❌ فشل {ch}: {e}")
        return None

async def main():
    logger.info("=" * 60)
    logger.info("🚀 بدء العملية")
    logger.info("=" * 60)
    
    # التحقق
    if not all([API_ID, API_HASH, SESSION, BOT_TOKEN, CHAT_ID]):
        logger.error("❌ إعدادات ناقصة!")
        return
    
    if not CHANNELS:
        logger.error("❌ لا توجد قنوات!")
        return
    
    # اختبار
    if not test_bot():
        logger.error("❌ فشل اختبار البوت")
        return
    
    # اختبار إرسال
    if not send_telegram("✅ <b>البوت يعمل!</b>\nبدء الجمع..."):
        logger.error("❌ فشل إرسال الاختبار")
        return
    
    logger.info("✅ الاختبار نجح!")
    
    # الجمع
    sent_links = load_sent_links()
    logger.info(f"📚 روابط محفوظة: {len(sent_links)}")
    
    all_items = []
    
    logger.info("🔌 الاتصال بـ Telegram...")
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"👤 متصل: {me.first_name} (@{me.username})")
        
        send_telegram(f"👤 <b>متصل:</b> {me.first_name}\n📡 <b>قنوات:</b> {len(CHANNELS)}")
        
        # معالجة كل قناة
        for idx, ch in enumerate(CHANNELS, 1):
            logger.info(f"\n{'='*40}")
            logger.info(f"📡 [{idx}/{len(CHANNELS)}] {ch}")
            logger.info(f"{'='*40}")
            
            channel = await resolve_channel(client, ch)
            if not channel:
                send_telegram(f"❌ فشل: <code>{ch}</code>")
                continue
            
            send_telegram(f"✅ <b>{channel.title}</b> - جاري الجمع...")
            
            count = 0
            ali_count = 0
            
            try:
                logger.info(f"📥 جمع من {channel.title}...")
                async for msg in client.iter_messages(channel, limit=50):
                    if not msg.message:
                        continue
                    
                    urls = re.findall(r'https?://\S+', msg.message)
                    
                    for url in urls:
                        url = url.rstrip('.,;:!?)]}>"\'')
                        
                        if url in sent_links:
                            continue
                        
                        # تسجيل
                        item = {
                            'url': url,
                            'channel': channel.title,
                            'text': msg.message[:100],
                            'is_ali': is_aliexpress(url),
                            'aff_url': None
                        }
                        
                        if item['is_ali']:
                            ali_count += 1
                            aff = add_affiliate(url)
                            if aff:
                                item['aff_url'] = aff
                                logger.info(f"💰 أفلييت: {url[:50]}...")
                        
                        all_items.append(item)
                        sent_links.append(url)
                        count += 1
                
                logger.info(f"📊 {channel.title}: {count} روابط ({ali_count} AliExpress)")
                send_telegram(f"📊 <b>{channel.title}</b>\nروابط: {count}\nAliExpress: {ali_count}")
                
            except Exception as e:
                logger.error(f"❌ خطأ في جمع {channel.title}: {e}")
                send_telegram(f"⚠️ خطأ في {channel.title}: {str(e)[:100]}")
            
            await asyncio.sleep(2)
        
        logger.info(f"\n{'='*40}")
        logger.info("📊 انتهى الجمع")
        logger.info(f"{'='*40}")
    
    # إرسال النتائج
    logger.info(f"📊 المجموع الكلي: {len(all_items)}")
    
    if all_items:
        save_sent_links(sent_links)
        
        ali_items = [i for i in all_items if i['is_ali']]
        aff_items = [i for i in all_items if i.get('aff_url')]
        
        logger.info(f"🛒 AliExpress: {len(ali_items)}")
        logger.info(f"💰 بأفلييت: {len(aff_items)}")
        
        # إرسال الروابط
        send_telegram(f"📤 <b>إرسال {min(len(all_items), 15)} رابط...</b>")
        
        for idx, item in enumerate(all_items[:15], 1):
            if item.get('aff_url'):
                display = item['aff_url']
                badge = "💰 أفلييت"
            elif item['is_ali']:
                display = item['url']
                badge = "🛒 AliExpress"
            else:
                display = item['url']
                badge = "🔗"
            
            msg = f"{badge} [{idx}/{min(len(all_items), 15)}]\n"
            msg += f"<b>{item['channel']}</b>\n\n"
            msg += f"<a href='{display}'>{display[:55]}...</a>\n\n"
            msg += f"📝 {item['text'][:70]}..."
            
            success = send_telegram(msg)
            if not success:
                logger.error(f"❌ فشل إرسال رابط {idx}")
            
            await asyncio.sleep(0.3)
        
        # ملخص
        summary = f"📊 <b>انتهى!</b>\n\n"
        summary += f"📡 قنوات: {len(CHANNELS)}\n"
        summary += f"🔗 إجمالي: {len(all_items)}\n"
        summary += f"🛒 AliExpress: {len(ali_items)}\n"
        summary += f"💰 بأفلييت: {len(aff_items)}\n"
        summary += f"📚 في DB: {len(sent_links)}"
        
        send_telegram(summary)
        logger.info("✅ تم إرسال الملخص")
        
    else:
        logger.info("📭 لا شيء جديد")
        send_telegram("📭 لا توجد روابط جديدة")
    
    logger.info("=" * 60)
    logger.info("✅ انتهى البرنامج بنجاح")
    logger.info("=" * 60)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # محاولة إرسال تنبيه
        try:
            send_telegram(f"❌ <b>خطأ:</b> <code>{str(e)[:200]}</code>")
        except:
            pass
