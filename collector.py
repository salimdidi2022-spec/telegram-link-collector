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
API_ID = int(os.environ.get('API_ID', '0'))
API_HASH = os.environ.get('API_HASH', '')
SESSION = os.environ.get('SESSION_STRING', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
CHAT_ID = os.environ.get('CHAT_ID', '')
CHANNELS_INPUT = os.environ.get('CHANNELS', '')

logger.info(f"🔧 التحقق من الإعدادات:")
logger.info(f"   API_ID: {'✅' if API_ID else '❌'}")
logger.info(f"   API_HASH: {'✅' if API_HASH else '❌'} ({len(API_HASH)} حرف)")
logger.info(f"   SESSION: {'✅' if SESSION else '❌'} ({len(SESSION) if SESSION else 0} حرف)")
logger.info(f"   BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'} ({len(BOT_TOKEN) if BOT_TOKEN else 0} حرف)")
logger.info(f"   CHAT_ID: {'✅' if CHAT_ID else '❌'} = {CHAT_ID}")
logger.info(f"   CHANNELS: {CHANNELS_INPUT[:50] if CHANNELS_INPUT else '❌'}")

CHANNELS = [c.strip() for c in CHANNELS_INPUT.split(',') if c.strip()] if CHANNELS_INPUT else []
logger.info(f"📡 عدد القنوات المparsed: {len(CHANNELS)}")

# AliExpress
ALI_APP_KEY = os.environ.get('ALI_APP_KEY', '')
ALI_APP_SECRET = os.environ.get('ALI_APP_SECRET', '')
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

def send_telegram(message):
    """إرسال رسالة مع تسجيل مفصل"""
    if not BOT_TOKEN or not CHAT_ID:
        logger.error("❌ BOT_TOKEN أو CHAT_ID غير موجود!")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    
    logger.info(f"📤 محاولة الإرسال لـ Chat ID: {CHAT_ID}")
    logger.info(f"   الرسالة: {message[:100]}...")
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        
        logger.info(f"   رد HTTP: {response.status_code}")
        logger.info(f"   محتوى الرد: {response.text[:200]}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                logger.info("✅ تم الإرسال بنجاح!")
                return True
            else:
                logger.error(f"❌ Telegram API رفض: {data}")
                return False
        else:
            logger.error(f"❌ خطأ HTTP: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ استثناء في الإرسال: {e}")
        return False

def test_bot():
    """اختبار البوت قبل البدء"""
    logger.info("🧪 اختبار الاتصال بالبوت...")
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN فارغ!")
        return False
    
    # اختبار بسيط - الحصول على معلومات البوت
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_info = data['result']
                logger.info(f"✅ البوت يعمل: @{bot_info['username']}")
                return True
        logger.error(f"❌ البوت لا يستجيب: {response.text}")
        return False
    except Exception as e:
        logger.error(f"❌ خطأ في اختبار البوت: {e}")
        return False

def is_aliexpress_link(url):
    url_lower = url.lower()
    return any(x in url_lower for x in ['aliexpress.com', 'aliexpress.us', 'a.aliexpress.com'])

def extract_product_id(url):
    patterns = [
        r'/item/(\d+)\.html',
        r'item_id=(\d+)',
        r'/product/(\d+)',
        r'/i/(\d+)\.html',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def generate_affiliate_link(url):
    """محاولة بسيطة لإنشاء رابط أفلييت"""
    if not ALI_APP_KEY:
        return None
    
    product_id = extract_product_id(url)
    if not product_id:
        return None
    
    # طريقة بسيطة - إضافة معلمات للرابط الأصلي
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    
    affiliate_params = {
        'aff_fcid': f'{ALI_APP_KEY}::{ALI_TRACKING_ID}',
        'aff_platform': 'default',
        'sk': ALI_APP_KEY,
        'aff_trace_key': f'{ALI_TRACKING_ID}_{int(time.time())}',
    }
    
    for k, v in affiliate_params.items():
        params[k] = [v]
    
    new_query = urlencode(params, doseq=True)
    new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    
    return {'short': new_url, 'full': new_url, 'product_id': product_id}

async def resolve_channel(client, channel_input):
    channel_input = channel_input.strip()
    logger.info(f"🔍 محاولة: {channel_input}")
    
    try:
        if channel_input.startswith('@'):
            entity = await client.get_entity(channel_input)
            return entity
        
        if 't.me/' in channel_input:
            path = urlparse(channel_input).path.strip('/')
            if path.startswith('+'):
                result = await client(CheckChatInviteRequest(path[1:]))
                return result.chat if hasattr(result, 'chat') else None
            else:
                return await client.get_entity('@' + path)
        
        return await client.get_entity('@' + channel_input)
    except Exception as e:
        logger.error(f"❌ فشل: {e}")
        return None

async def main():
    logger.info("=" * 60)
    logger.info("🚀 بدء العملية")
    logger.info("=" * 60)
    
    # ========== التحقق من الإعدادات ==========
    if not all([API_ID, API_HASH, SESSION, BOT_TOKEN, CHAT_ID]):
        logger.error("❌ إعدادات ناقصة! تحقق من Secrets.")
        return
    
    if not CHANNELS:
        logger.error("❌ لا توجد قنوات!")
        return
    
    # اختبار البوت أولاً
    if not test_bot():
        logger.error("❌ فشل اختبار البوت! توقف.")
        return
    
    # اختبار إرسال رسالة
    logger.info("🧪 إرسال رسالة اختبار...")
    test_msg = "✅ <b>البوت يعمل!</b>\nبدء جمع الروابط..."
    if not send_telegram(test_msg):
        logger.error("❌ فشل إرسال رسالة الاختبار!")
        return
    
    # ========== بدء الجمع ==========
    sent_links = load_sent_links()
    logger.info(f"📚 روابط محفوظة: {len(sent_links)}")
    
    all_items = []
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"✅ متصل: {me.first_name}")
        
        # إرسال تأكيد الاتصال
        send_telegram(f"👤 متصل بحساب: {me.first_name}\n📡 جمع من {len(CHANNELS)} قنوات...")
        
        for idx, ch in enumerate(CHANNELS, 1):
            logger.info(f"\n📡 [{idx}/{len(CHANNELS)}] {ch}")
            
            channel = await resolve_channel(client, ch)
            if not channel:
                send_telegram(f"❌ فشل الاتصال بـ: {ch}")
                continue
            
            send_telegram(f"✅ متصل بـ: <b>{channel.title}</b>")
            
            # جمع الرسائل
            new_count = 0
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
                        'is_aliexpress': is_aliexpress_link(url),
                        'affiliate_url': None
                    }
                    
                    # محاولة تحويل AliExpress
                    if item['is_aliexpress']:
                        aff = generate_affiliate_link(url)
                        if aff:
                            item['affiliate_url'] = aff['short']
                            item['product_id'] = aff['product_id']
                    
                    all_items.append(item)
                    sent_links.append(url)
                    new_count += 1
                    
                    await asyncio.sleep(0.3)
            
            logger.info(f"📊 {channel.title}: {new_count} جديد")
            send_telegram(f"📊 {channel.title}: <b>{new_count}</b> رابط جديد")
            await asyncio.sleep(2)
    
    # ========== إرسال النتائج ==========
    logger.info(f"\n📊 الإجمالي: {len(all_items)}")
    
    if all_items:
        save_sent_links(sent_links)
        
        # إحصائيات
        ali_items = [i for i in all_items if i['is_aliexpress']]
        converted = [i for i in ali_items if i.get('affiliate_url')]
        
        # إرسال الروابط
        for item in all_items[:20]:  # أول 20 فقط
            if item['is_aliexpress'] and item.get('affiliate_url'):
                display_url = item['affiliate_url']
                badge = "💰 أفلييت"
            elif item['is_aliexpress']:
                display_url = item['url']
                badge = "🛒 AliExpress"
            else:
                display_url = item['url']
                badge = "🔗 رابط"
            
            msg = f"{badge}\n<b>{item['channel']}</b>\n\n"
            msg += f"<a href='{display_url}'>{display_url[:50]}...</a>\n\n"
            msg += f"📝 {item['text'][:60]}..."
            
            send_telegram(msg)
            await asyncio.sleep(1)
        
        # ملخص
        summary = f"📊 <b>انتهى الجمع</b>\n\n"
        summary += f"🛒 AliExpress: {len(ali_items)}\n"
        summary += f"💰 بأفلييت: {len(converted)}\n"
        summary += f"🔗 إجمالي: {len(all_items)}"
        send_telegram(summary)
        
    else:
        logger.info("📭 لا شيء جديد")
        send_telegram("📭 لا توجد روابط جديدة في هذه الجولة")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        # محاولة إرسال تنبيه
        try:
            send_telegram(f"❌ <b>خطأ في البوت:</b>\n<code>{str(e)[:200]}</code>")
        except:
            pass
