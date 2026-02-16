import os
import asyncio
import logging
import json
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CheckChatInviteRequest
import requests
import re
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# الإعدادات
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
SESSION = os.environ['SESSION_STRING']
BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID = os.environ['CHAT_ID']

# قراءة القنوات (مفصولة بفواصل)
CHANNELS_INPUT = os.environ.get('CHANNELS', os.environ.get('CHANNEL', ''))
CHANNELS = [c.strip() for c in CHANNELS_INPUT.split(',') if c.strip()]

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

async def resolve_channel(client, channel_input):
    """حل أي شكل من أشكال روابط القنوات"""
    channel_input = channel_input.strip()
    logger.info(f"🔍 محاولة: {channel_input}")
    
    # @channel_name
    if channel_input.startswith('@'):
        try:
            return await client.get_entity(channel_input)
        except Exception as e:
            logger.error(f"❌ فشل @: {e}")
            return None
    
    # رابط t.me
    if 't.me/' in channel_input:
        path = urlparse(channel_input).path.strip('/')
        
        # رابط دعوة خاص
        if path.startswith('+'):
            try:
                result = await client(CheckChatInviteRequest(path[1:]))
                return result.chat if hasattr(result, 'chat') else None
            except Exception as e:
                logger.error(f"❌ فشل دعوة: {e}")
                return None
        else:
            # رابط عام
            try:
                return await client.get_entity('@' + path)
            except:
                return None
    
    # بدون @
    try:
        return await client.get_entity('@' + channel_input)
    except:
        pass
    
    return None

async def collect_from_channel(client, channel_input, sent_links):
    """جمع الروابط من قناة واحدة"""
    channel = await resolve_channel(client, channel_input)
    
    if not channel:
        logger.error(f"❌ لم أجد: {channel_input}")
        return []
    
    logger.info(f"✅ متصل بـ: {channel.title}")
    
    new_links = []
    
    async for msg in client.iter_messages(channel, limit=50):
        if msg.message:
            urls = re.findall(r'https?://\S+', msg.message)
            
            for url in urls:
                url = url.rstrip('.,;:!?)]}')
                
                if url not in sent_links:
                    new_links.append({
                        'url': url,
                        'channel': channel.title,
                        'text': msg.message[:80] if msg.message else '',
                        'date': str(msg.date)[:16] if msg.date else ''
                    })
                    sent_links.append(url)
    
    logger.info(f"📊 {channel.title}: {len(new_links)} رابط جديد")
    return new_links

async def main():
    logger.info(f"🚀 بدء جمع من {len(CHANNELS)} قنوات")
    
    sent_links = load_sent_links()
    logger.info(f"📚 روابط محفوظة: {len(sent_links)}")
    
    all_new_links = []
    
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"✅ متصل كـ: {me.first_name}")
        
        # جمع من كل قناة
        for ch in CHANNELS:
            links = await collect_from_channel(client, ch, sent_links)
            all_new_links.extend(links)
            await asyncio.sleep(2)  # انتظار بين القنوات
    
    # حفظ وإرسال النتائج
    if all_new_links:
        save_sent_links(sent_links)
        
        # تجميع حسب القناة
        by_channel = {}
        for link in all_new_links:
            ch = link['channel']
            if ch not in by_channel:
                by_channel[ch] = []
            by_channel[ch].append(link)
        
        # إرسال رسالة لكل قناة
        for channel_name, links in by_channel.items():
            for i in range(0, len(links), 10):
                batch = links[i:i+10]
                
                msg = f"🆕 <b>{len(links)} رابط جديد من {channel_name}</b>\n\n"
                
                for idx, link in enumerate(batch, i+1):
                    preview = link['text'][:50] + "..." if len(link['text']) > 50 else link['text']
                    msg += f"{idx}. <a href='{link['url']}'>{link['url'][:45]}...</a>\n"
                    msg += f"   📝 {preview}\n\n"
                
                send(msg)
                await asyncio.sleep(1)
        
        # ملخص إجمالي
        summary = f"📊 <b>ملخص الجولة</b>\n\n"
        summary += f"📡 القنوات: {len(CHANNELS)}\n"
        summary += f"🔗 الروابط الجديدة: {len(all_new_links)}\n"
        summary += f"📚 إجمالي الروابط المحفوظة: {len(sent_links)}"
        send(summary)
        
        logger.info(f"✅ أرسلت {len(all_new_links)} رابط من {len(by_channel)} قناة")
    else:
        logger.info("📭 لا توجد روابط جديدة من أي قناة")

asyncio.run(main())
