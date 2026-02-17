import os
import asyncio
import logging
import json
import hashlib
import hmac
import time
import base64
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CheckChatInviteRequest
import requests
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# إعدادات Telegram
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
SESSION = os.environ['SESSION_STRING']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID = os.environ['CHAT_ID']
CHANNELS_INPUT = os.environ.get('CHANNELS', '')
CHANNELS = [c.strip() for c in CHANNELS_INPUT.split(',') if c.strip()]

# إعدادات AliExpress
ALI_APP_KEY = os.environ.get('ALI_APP_KEY', '')
ALI_APP_SECRET = os.environ.get('ALI_APP_SECRET', '')
ALI_TRACKING_ID = os.environ.get('ALI_TRACKING_ID', 'default')

DB_FILE = 'sent_links.json'

def load_sent_links():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_sent_links(links):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, indent=2)

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={
            'chat_id': CHAT_ID,
            'text': msg,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }, timeout=10)
        if response.status_code == 200:
            logger.info("✅ تم إرسال الرسالة")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ خطأ في الإرسال: {e}")
        return False

def is_aliexpress_link(url):
    """التحقق من أن الرابط لـ AliExpress"""
    url_lower = url.lower()
    ali_domains = [
        'aliexpress.com', 'aliexpress.us', 'a.aliexpress.com',
        's.click.aliexpress.com', 'www.aliexpress.com',
        'm.aliexpress.com', 'aliexpress.ru'
    ]
    return any(domain in url_lower for domain in ali_domains)

def extract_product_info(url):
    """استخراج معرف المنتج والاسم من رابط AliExpress"""
    try:
        # أنماط مختلفة لروابط AliExpress
        patterns = [
            r'/item/(\d+)\.html',
            r'item_id=(\d+)',
            r'/product/(\d+)',
            r'/i/(\d+)\.html',
            r'products/(\d+)',
            r'p/(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return {'product_id': match.group(1), 'type': 'product'}
        
        # رابط قصير a.aliexpress.com
        if 'a.aliexpress.com' in url:
            return {'short_link': url, 'type': 'short'}
        
        return None
    except Exception as e:
        logger.error(f"❌ خطأ في استخراج المعلومات: {e}")
        return None

def generate_affiliate_link_api(url):
    """
    توليد رابط أفلييت باستخدام AliExpress API
    """
    if not ALI_APP_KEY or not ALI_APP_SECRET:
        logger.warning("⚠️ لا توجد بيانات API")
        return None
    
    product_info = extract_product_info(url)
    if not product_info:
        logger.warning(f"⚠️ لم أستطع استخراج معرف من: {url[:60]}")
        return None
    
    logger.info(f"🔍 معلومات المنتج: {product_info}")
    
    # AliExpress Affiliate API v2
    api_url = "https://eco.taobao.com/router/rest"
    
    # المعلمات الأساسية
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    params = {
        'app_key': ALI_APP_KEY,
        'format': 'json',
        'method': 'aliexpress.affiliate.link.generate',
        'partner_id': 'top-sdk-python-2024',
        'sign_method': 'md5',
        'timestamp': timestamp,
        'v': '2.0',
        'tracking_id': ALI_TRACKING_ID,
        'promotion_link_type': '0',
        'source_values': product_info.get('product_id', url),
    }
    
    # إنشاء التوقيع
    sorted_params = sorted(params.items())
    sign_string = ALI_APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted_params]) + ALI_APP_SECRET
    sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest().upper()
    params['sign'] = sign
    
    try:
        logger.info(f"🌐 إرسال طلب لـ API...")
        response = requests.get(api_url, params=params, timeout=20)
        logger.info(f"📥 رد API: {response.status_code}")
        
        data = response.json()
        logger.debug(f"رد كامل: {json.dumps(data, indent=2)[:500]}")
        
        # التحقق من وجود خطأ
        if 'error_response' in data:
            error = data['error_response']
            logger.error(f"❌ خطأ API: {error.get('msg', 'غير معروف')}")
            return None
        
        # استخراج الرابط
        response_key = 'aliexpress_affiliate_link_generate_response'
        if response_key in data:
            result = data[response_key]
            
            if 'promotion_links' in result and result['promotion_links']:
                links_data = result['promotion_links'].get('promotion_link', [])
                
                if links_data and len(links_data) > 0:
                    link_info = links_data[0]
                    affiliate_url = link_info.get('promotion_link')
                    short_url = link_info.get('short_link', affiliate_url)
                    
                    if affiliate_url:
                        logger.info(f"✅ تم إنشاء رابط أفلييت")
                        return {
                            'full': affiliate_url,
                            'short': short_url,
                            'product_id': product_info.get('product_id')
                        }
        
        logger.error(f"❌ لم أجد رابط في الرد: {str(data)[:200]}")
        return None
        
    except Exception as e:
        logger.error(f"❌ استثناء في API: {e}")
        return None

def generate_affiliate_link_portal(url):
    """
    طريقة بديلة: استخدام رابط مباشر من البوابة
    """
    try:
        # توليد رابط بسيط باستخدام معلمات التتبع
        if 'aliexpress.com' in url:
            # إضافة معلمات الأفلييت للرابط المباشر
            parsed = urlparse(url)
            
            # معلمات الأفلييت
            affiliate_params = {
                'aff_fcid': f'{ALI_APP_KEY}::{ALI_TRACKING_ID}',
                'aff_fsk': ALI_APP_KEY,
                'aff_platform': 'default',
                'aff_trace_key': f'{ALI_TRACKING_ID}_{int(time.time())}',
                'terminal_id': 'telebot',
                'tmLog': 'default_Deeplink'
            }
            
            # دمج المعلمات الموجودة مع الجديدة
            existing_params = parse_qs(parsed.query)
            for k, v in affiliate_params.items():
                existing_params[k] = [v]
            
            new_query = urlencode(existing_params, doseq=True)
            new_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
            
            return {
                'full': new_url,
                'short': new_url,
                'method': 'portal_direct'
            }
        
        return None
    except Exception as e:
        logger.error(f"❌ خطأ في Portal method: {e}")
        return None

def generate_affiliate_link_admitad(url):
    """
    طريقة ثالثة: استخدام Admitad (إذا كان لديك حساب)
    """
    # يمكنك إضافة رابط Admitad هنا إذا كان لديك
    return None

def convert_to_affiliate(url):
    """
    محاولة تحويل الرابط بجميع الطرق المتاحة
    """
    logger.info(f"🔄 محاولة تحويل: {url[:70]}...")
    
    # المحاولة 1: API الرسمي
    result = generate_affiliate_link_api(url)
    if result:
        logger.info("✅ تم التحويل عبر API")
        return result
    
    # المحاولة 2: طريقة البوابة المباشرة
    result = generate_affiliate_link_portal(url)
    if result:
        logger.info("✅ تم التحويل عvia Portal")
        return result
    
    # المحاولة 3: Admitad أو شبكات أخرى
    result = generate_affiliate_link_admitad(url)
    if result:
        logger.info("✅ تم التحويل عبر شبكة خارجية")
        return result
    
    logger.warning("❌ فشلت جميع محاولات التحويل")
    return None

async def resolve_channel(client, channel_input):
    channel_input = channel_input.strip()
    logger.info(f"🔍 محاولة الاتصال بـ: {channel_input}")
    
    if channel_input.startswith('@'):
        try:
            entity = await client.get_entity(channel_input)
            logger.info(f"✅ تم الاتصال بـ @{channel_input}")
            return entity
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بـ @{channel_input}: {e}")
            return None
    
    if 't.me/' in channel_input:
        path = urlparse(channel_input).path.strip('/')
        
        if path.startswith('+'):
            try:
                result = await client(CheckChatInviteRequest(path[1:]))
                if hasattr(result, 'chat'):
                    logger.info(f"✅ تم الانضمام بالدعوة: {result.chat.title}")
                    return result.chat
            except Exception as e:
                logger.error(f"❌ فشل الانضمام بالدعوة: {e}")
                return None
        else:
            try:
                entity = await client.get_entity('@' + path)
                logger.info(f"✅ تم الاتصال برابط t.me")
                return entity
            except Exception as e:
                logger.error(f"❌ فشل الاتصال برابط t.me: {e}")
                return None
    
    try:
        entity = await client.get_entity('@' + channel_input)
        logger.info(f"✅ تم الاتصال بدون @")
        return entity
    except:
        pass
    
    logger.error(f"❌ لم أتمكن من حل: {channel_input}")
    return None

async def collect_from_channel(client, channel_input, sent_links):
    channel = await resolve_channel(client, channel_input)
    
    if not channel:
        return []
    
    logger.info(f"📥 جمع من: {channel.title}")
    
    new_items = []
    
    try:
        async for message in client.iter_messages(channel, limit=50):
            if not message.message:
                continue
            
            urls = re.findall(r'https?://\S+', message.message)
            
            for url in urls:
                url = url.rstrip('.,;:!?)]}>"\'')
                
                if url in sent_links:
                    continue
                
                item = {
                    'original_url': url,
                    'channel': channel.title,
                    'text': message.message[:100] if message.message else '',
                    'date': str(message.date)[:16] if message.date else '',
                    'is_aliexpress': False,
                    'affiliate_url': None,
                    'product_id': None,
                    'conversion_method': None
                }
                
                # التحقق من AliExpress وتحويله
                if is_aliexpress_link(url):
                    item['is_aliexpress'] = True
                    logger.info(f"🛒 AliExpress مكتشف: {url[:60]}...")
                    
                    affiliate_result = convert_to_affiliate(url)
                    
                    if affiliate_result:
                        item['affiliate_url'] = affiliate_result.get('short') or affiliate_result.get('full')
                        item['product_id'] = affiliate_result.get('product_id')
                        item['conversion_method'] = affiliate_result.get('method', 'api')
                        logger.info(f"✅ تم التحويل: {item['affiliate_url'][:60]}...")
                    else:
                        logger.warning(f"⚠️ لم يتم التحويل، سيتم استخدام الرابط الأصلي")
                
                new_items.append(item)
                sent_links.append(url)
                
                # تأخير قصير لتجنب الحظر
                await asyncio.sleep(0.5)
        
        logger.info(f"📊 تم جمع {len(new_items)} عنصر جديد من {channel.title}")
        
    except Exception as e:
        logger.error(f"❌ خطأ أثناء جمع {channel.title}: {e}")
    
    return new_items

async def main():
    logger.info("="*60)
    logger.info("🚀 بدء جمع الروابط")
    logger.info(f"📡 القنوات: {len(CHANNELS)}")
    logger.info(f"🛒 AliExpress API: {'مفعل' if ALI_APP_KEY else 'غير مفعل'}")
    logger.info("="*60)
    
    sent_links = load_sent_links()
    logger.info(f"📚 الروابط المحفوظة سابقاً: {len(sent_links)}")
    
    all_items = []
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"✅ متصل بحساب: {me.first_name} (@{me.username})")
        
        for idx, ch in enumerate(CHANNELS, 1):
            logger.info(f"\n📡 [{idx}/{len(CHANNELS)}] معالجة: {ch}")
            items = await collect_from_channel(client, ch, sent_links)
            all_items.extend(items)
            
            # تأخير بين القنوات
            if idx < len(CHANNELS):
                await asyncio.sleep(3)
    
    logger.info(f"\n📊 إجمالي العناصر الجديدة: {len(all_items)}")
    
    if all_items:
        # حفظ الروابط
        save_sent_links(sent_links)
        logger.info(f"💾 تم حفظ {len(sent_links)} رابط في قاعدة البيانات")
        
        # إحصائيات
        ali_items = [i for i in all_items if i['is_aliexpress']]
        converted_items = [i for i in ali_items if i.get('affiliate_url')]
        
        logger.info(f"🛒 منتجات AliExpress: {len(ali_items)}")
        logger.info(f"💰 محولة لأفلييت: {len(converted_items)}")
        logger.info(f"📉 فشل التحويل: {len(ali_items) - len(converted_items)}")
        
        # تجميع حسب القناة
        by_channel = {}
        for item in all_items:
            ch = item['channel']
            if ch not in by_channel:
                by_channel[ch] = {'all': [], 'ali': [], 'converted': []}
            by_channel[ch]['all'].append(item)
            if item['is_aliexpress']:
                by_channel[ch]['ali'].append(item)
                if item.get('affiliate_url'):
                    by_channel[ch]['converted'].append(item)
        
        # إرسال النتائج
        for channel_name, data in by_channel.items():
            ali_list = data['ali']
            other_list = [i for i in data['all'] if not i['is_aliexpress']]
            
            # إرسال منتجات AliExpress
            if ali_list:
                for i in range(0, len(ali_list), 5):
                    batch = ali_list[i:i+5]
                    
                    msg = f"🛒 <b>منتجات AliExpress من {channel_name}</b>\n"
                    msg += f"💰 {len([x for x in batch if x.get('affiliate_url')])}/{len(batch)} محولة\n\n"
                    
                    for idx, item in enumerate(batch, i+1):
                        # استخدام رابط الأفلييت إذا وجد
                        display_url = item.get('affiliate_url') or item['original_url']
                        is_converted = "✅" if item.get('affiliate_url') else "⚠️"
                        
                        preview = item['text'][:35] + "..." if len(item['text']) > 35 else item['text']
                        product_id = item.get('product_id') or '??'
                        
                        msg += f"{is_converted} {idx}. <a href='{display_url}'>منتج #{product_id}</a>\n"
                        msg += f"   📝 {preview}\n"
                        if item.get('affiliate_url'):
                            msg += f"   💎 رابط أفلييت\n"
                        msg += "\n"
                    
                    send(msg)
                    await asyncio.sleep(1)
            
            # إرسال الروابط العادية
            if other_list:
                for i in range(0, len(other_list), 10):
                    batch = other_list[i:i+10]
                    
                    msg = f"🔗 <b>روابط من {channel_name}</b>\n\n"
                    
                    for idx, item in enumerate(batch, i+1):
                        preview = item['text'][:40] + "..." if len(item['text']) > 40 else item['text']
                        msg += f"{idx}. <a href='{item['original_url']}'>{item['original_url'][:45]}...</a>\n"
                        msg += f"   📝 {preview}\n\n"
                    
                    send(msg)
                    await asyncio.sleep(1)
        
        # ملخص إجمالي
        total_ali = len(ali_items)
        total_converted = len(converted_items)
        conversion_rate = (total_converted / total_ali * 100) if total_ali > 0 else 0
        
        summary = f"📊 <b>ملخص الجولة</b>\n\n"
        summary += f"📡 القنوات المعالجة: {len(CHANNELS)}\n"
        summary += f"🛒 منتجات AliExpress: {total_ali}\n"
        summary += f"💰 محولة لأفلييت: {total_converted} ({conversion_rate:.1f}%)\n"
        summary += f"🔗 روابط عادية: {len(all_items) - total_ali}\n"
        summary += f"📚 إجمالي المحفوظ: {len(sent_links)}\n"
        
        if total_converted < total_ali:
            summary += f"\n⚠️ <b>تنبيه:</b> {total_ali - total_converted} منتج لم يتحول\n"
            summary += f"تحقق من بيانات API في الإعدادات"
        
        send(summary)
        logger.info("✅ تم إرسال الملخص")
        
    else:
        logger.info("📭 لا توجد روابط جديدة")
        # رسالة تأكيد كل 6 ساعات (اختياري)
        # send("✅ فحص دوري: لا توجد روابط جديدة")

if __name__ == '__main__':
    asyncio.run(main())
