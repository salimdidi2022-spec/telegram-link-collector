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
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات Telegram
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
SESSION = os.environ['SESSION_STRING']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID = os.environ['CHAT_ID']
CHANNELS_INPUT = os.environ.get('CHANNELS', '')
CHANNELS = [c.strip() for c in CHANNELS_INPUT.split(',') if c.strip()]

# إعدادات AliExpress Affiliate
ALI_APP_KEY = os.environ.get('ALI_APP_KEY', '')
ALI_APP_SECRET = os.environ.get('ALI_APP_SECRET', '')
ALI_TRACKING_ID = os.environ.get('ALI_TRACKING_ID', '')  # مثال: default, winter2024, etc.

DB_FILE = 'sent_links.json'

def load_sent_links():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return []

def save_sent_links(links):
    with open(DB_FILE, 'w') as f:
        json.dump(links, f)

def send(msg):
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

def is_aliexpress_link(url):
    """التحقق من أن الرابط لـ AliExpress"""
    ali_domains = [
        'aliexpress.com', 'aliexpress.us', 'a.aliexpress.com',
        's.click.aliexpress.com', 'www.aliexpress.com'
    ]
    url_lower = url.lower()
    return any(domain in url_lower for domain in ali_domains)

def extract_product_id(url):
    """استخراج معرف المنتج من رابط AliExpress"""
    try:
        # نمط 1: /item/1234567890.html
        match = re.search(r'/item/(\d+)\.html', url)
        if match:
            return match.group(1)
        
        # نمط 2: ?item_id=1234567890
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if 'item_id' in params:
            return params['item_id'][0]
        
        # نمط 3: /product/1234567890
        match = re.search(r'/product/(\d+)', url)
        if match:
            return match.group(1)
        
        # نمط 4: /i/1234567890.html
        match = re.search(r'/i/(\d+)\.html', url)
        if match:
            return match.group(1)
        
        return None
    except:
        return None

def generate_affiliate_link_v2(original_url):
    """
    توليد رابط أفلييت باستخدام AliExpress API v2
    """
    if not ALI_APP_KEY or not ALI_APP_SECRET:
        logger.warning("⚠️ لا توجد بيانات AliExpress API")
        return None
    
    product_id = extract_product_id(original_url)
    if not product_id:
        logger.warning(f"⚠️ لم أجد معرف المنتج في: {original_url[:50]}")
        return None
    
    logger.info(f"🔍 معرف المنتج: {product_id}")
    
    # AliExpress Affiliate API v2
    api_url = "https://open-api.aliexpress.com/sync"
    
    # المعلمات الأساسية
    params = {
        'app_key': ALI_APP_KEY,
        'timestamp': str(int(time.time() * 1000)),
        'sign_method': 'md5',
        'partner_id': 'top-sdk-js-2024',
        'format': 'json',
        'method': 'aliexpress.affiliate.link.generate',
        'tracking_id': ALI_TRACKING_ID or 'default',
        'promotion_link_type': '0',  # 0 = عادي, 2 = قصير
        'source_values': product_id,
        'app_signature': ''
    }
    
    # ترتيب المعلمات للتوقيع
    sorted_params = sorted(params.items())
    sign_string = ALI_APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted_params]) + ALI_APP_SECRET
    
    # إنشاء التوقيع MD5
    sign = hashlib.md5(sign_string.encode()).hexdigest().upper()
    params['sign'] = sign
    
    try:
        response = requests.get(api_url, params=params, timeout=15)
        data = response.json()
        
        if 'aliexpress_affiliate_link_generate_response' in data:
            result = data['aliexpress_affiliate_link_generate_response']
            
            if 'promotion_links' in result and 'promotion_link' in result['promotion_links']:
                affiliate_url = result['promotion_links']['promotion_link'][0]['promotion_link']
                short_link = result['promotion_links']['promotion_link'][0].get('short_link', affiliate_url)
                
                logger.info(f"✅ تم إنشاء رابط أفلييت")
                return {
                    'full': affiliate_url,
                    'short': short_link,
                    'product_id': product_id
                }
        
        logger.error(f"❌ فشل API: {data}")
        return None
        
    except Exception as e:
        logger.error(f"❌ خطأ في API: {e}")
        return None

def generate_simple_affiliate_link(original_url):
    """
    طريقة بسيطة: إضافة معلمات التتبع للرابط المباشر
    (بدون API، تعمل فقط للروابط المختصرة)
    """
    try:
        parsed = urlparse(original_url)
        
        # إذا كان رابط a.aliexpress.com (مختصر)
        if 'a.aliexpress.com' in original_url:
            params = {
                'af': ALI_TRACKING_ID or 'default',
                'cv': '47843',
                'cn': '32342342342',
                'dp': 'v5_32342342342',
                'afref': f'https://t.me/your_channel'
            }
            
            new_query = urlencode(params)
            new_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
            return {'short': new_url, 'full': new_url, 'method': 'simple'}
        
        return None
        
    except Exception as e:
        logger.error(f"خطأ في الرابط البسيط: {e}")
        return None

async def resolve_channel(client, channel_input):
    channel_input = channel_input.strip()
    logger.info(f"🔍 محاولة: {channel_input}")
    
    if channel_input.startswith('@'):
        try:
            return await client.get_entity(channel_input)
        except Exception as e:
            logger.error(f"❌ فشل @: {e}")
            return None
    
    if 't.me/' in channel_input:
        path = urlparse(channel_input).path.strip('/')
        
        if path.startswith('+'):
            try:
                result = await client(CheckChatInviteRequest(path[1:]))
                return result.chat if hasattr(result, 'chat') else None
            except Exception as e:
                logger.error(f"❌ فشل دعوة: {e}")
                return None
        else:
            try:
                return await client.get_entity('@' + path)
            except:
                return None
    
    try:
        return await client.get_entity('@' + channel_input)
    except:
        pass
    
    return None

async def collect_from_channel(client, channel_input, sent_links):
    channel = await resolve_channel(client, channel_input)
    
    if not channel:
        logger.error(f"❌ لم أجد: {channel_input}")
        return []
    
    logger.info(f"✅ متصل بـ: {channel.title}")
    
    new_items = []
    
    async for msg in client.iter_messages(channel, limit=50):
        if msg.message:
            urls = re.findall(r'https?://\S+', msg.message)
            
            for url in urls:
                url = url.rstrip('.,;:!?)]}')
                
                # تجاهل الروابط المكررة
                if url in sent_links:
                    continue
                
                item = {
                    'original_url': url,
                    'channel': channel.title,
                    'text': msg.message[:100] if msg.message else '',
                    'date': str(msg.date)[:16] if msg.date else '',
                    'is_aliexpress': False,
                    'affiliate_url': None,
                    'product_id': None
                }
                
                # إذا كان رابط AliExpress، حوله لأفلييت
                if is_aliexpress_link(url):
                    item['is_aliexpress'] = True
                    logger.info(f"🛒 AliExpress: {url[:60]}...")
                    
                    # محاولة API v2 أولاً
                    affiliate = generate_affiliate_link_v2(url)
                    
                    # إذا فشل، جرب الطريقة البسيطة
                    if not affiliate:
                        affiliate = generate_simple_affiliate_link(url)
                    
                    if affiliate:
                        item['affiliate_url'] = affiliate.get('short', affiliate.get('full'))
                        item['product_id'] = affiliate.get('product_id')
                        logger.info(f"✅ أفلييت: {item['affiliate_url'][:60]}...")
                    else:
                        logger.warning(f"⚠️ لم أستطع تحويل: {url[:50]}")
                
                new_items.append(item)
                sent_links.append(url)
    
    logger.info(f"📊 {channel.title}: {len(new_items)} عنصر جديد")
    return new_items

async def main():
    logger.info(f"🚀 بدء جمع من {len(CHANNELS)} قنوات")
    logger.info(f"🛒 AliExpress API: {'مفعل' if ALI_APP_KEY else 'غير مفعل'}")
    
    sent_links = load_sent_links()
    logger.info(f"📚 روابط محفوظة: {len(sent_links)}")
    
    all_items = []
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"✅ متصل كـ: {me.first_name}")
        
        for ch in CHANNELS:
            items = await collect_from_channel(client, ch, sent_links)
            all_items.extend(items)
            await asyncio.sleep(2)
    
    if all_items:
        save_sent_links(sent_links)
        
        # تجميع حسب القناة
        by_channel = {}
        for item in all_items:
            ch = item['channel']
            if ch not in by_channel:
                by_channel[ch] = []
            by_channel[ch].append(item)
        
        # إرسال النتائج
        for channel_name, items in by_channel.items():
            # فصل AliExpress عن الباقي
            ali_items = [i for i in items if i['is_aliexpress']]
            other_items = [i for i in items if not i['is_aliexpress']]
            
            # إرسال روابط AliExpress مع أفلييت
            if ali_items:
                for i in range(0, len(ali_items), 5):
                    batch = ali_items[i:i+5]
                    
                    msg = f"🛒 <b>{len(ali_items)} منتج AliExpress من {channel_name}</b>\n"
                    msg += f"💰 روابط أفلييت مفعلة\n\n"
                    
                    for idx, item in enumerate(batch, i+1):
                        # استخدام رابط الأفلييت إذا وجد، وإلا الرابط الأصلي
                        display_url = item.get('affiliate_url') or item['original_url']
                        
                        # تقصير النص
                        preview = item['text'][:40] + "..." if len(item['text']) > 40 else item['text']
                        
                        msg += f"{idx}. <a href='{display_url}'>🛍️ منتج #{item.get('product_id', '??')}</a>\n"
                        if item.get('affiliate_url'):
                            msg += f"   💎 رابط مخصص لك\n"
                        msg += f"   📝 {preview}\n\n"
                    
                    send(msg)
                    await asyncio.sleep(1)
            
            # إرسال الروابط العادية (غير AliExpress)
            if other_items:
                for i in range(0, len(other_items), 10):
                    batch = other_items[i:i+10]
                    
                    msg = f"🔗 <b>{len(other_items)} رابط من {channel_name}</b>\n\n"
                    
                    for idx, item in enumerate(batch, i+1):
                        preview = item['text'][:40] + "..." if len(item['text']) > 40 else item['text']
                        msg += f"{idx}. <a href='{item['original_url']}'>{item['original_url'][:45]}...</a>\n"
                        msg += f"   📝 {preview}\n\n"
                    
                    send(msg)
                    await asyncio.sleep(1)
        
        # ملخص إجمالي
        total_ali = len([i for i in all_items if i['is_aliexpress']])
        total_converted = len([i for i in all_items if i.get('affiliate_url')])
        
        summary = f"📊 <b>ملخص الجولة</b>\n\n"
        summary += f"📡 القنوات: {len(CHANNELS)}\n"
        summary += f"🛒 منتجات AliExpress: {total_ali}\n"
        summary += f"💰 محولة لأفلييت: {total_converted}\n"
        summary += f"🔗 إجمالي جديد: {len(all_items)}\n"
        summary += f"📚 في قاعدة البيانات: {len(sent_links)}"
        send(summary)
        
        logger.info(f"✅ أرسلت {len(all_items)} عنصر")
    else:
        logger.info("📭 لا توجد روابط جديدة")

asyncio.run(main())
