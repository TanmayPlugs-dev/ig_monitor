# ============================================================
# Discord Instagram Monitor Bot
# Dev: TanmayPlugs
# ============================================================

import os
import sys
import asyncio
import random
import time
import re
from datetime import datetime

# Install packages automatically
try:
    import subprocess
    packages = ['discord.py', 'aiohttp', 'instaloader']

    for package in packages:
        try:
            if package == 'discord.py':
                import discord
            elif package == 'aiohttp':
                import aiohttp
            elif package == 'instaloader':
                import instaloader
        except:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
except:
    pass

import discord
from discord.ext import commands
import aiohttp
import instaloader

# ============================================================
# CONFIG
# ============================================================

TOKEN = "MTUwNzQ3Nzc1NTk4ODU0NTU3OA.GzzNIj.Q9eoVycSeKht4FFX2HOpCBdYd995Vg3HiX-Mec"
ALERT_CHANNEL_ID = 1507480464519331840

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ============================================================
# STORAGE
# ============================================================

tracked_accounts = {}
admins = set()
OWNER_ID = 1433932182979874949 # Your Discord User ID
monitoring_tasks = {}
alert_history = {}

CHECK_INTERVALS = {
    'ultra': 10,
    'fast': 30,
    'normal': 60,
    'slow': 300
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Instagram 269.0.0.18.75 Android',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)'
]

# ============================================================
# FETCH INSTAGRAM DATA
# ============================================================

async def fetch_instagram_data(username):
    username = username.lstrip('@').lower()

    try:
        L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            save_metadata=False,
            quiet=True,
            max_connection_attempts=1,
            request_timeout=15
        )

        L.context._session.headers.update({
            'User-Agent': random.choice(USER_AGENTS)
        })

        profile = instaloader.Profile.from_username(L.context, username)

        return {
            'success': True,
            'username': profile.username,
            'full_name': profile.full_name or username,
            'biography': profile.biography or '',
            'followers': profile.followers,
            'following': profile.followees,
            'posts': profile.mediacount,
            'profile_pic_url': profile.profile_pic_url,
            'is_private': profile.is_private,
            'is_verified': profile.is_verified,
            'timestamp': time.time(),
            'method': 'instaloader'
        }

    except:
        return {
            'success': False,
            'username': username,
            'error': 'Account not found'
        }

# ============================================================
# BAN CHANCE ANALYZER
# ============================================================

def calculate_ban_risk(data):
    """Estimate Instagram ban risk percentage"""

    risk = 0
    reasons = []

    followers = data.get('followers', 0)
    following = data.get('following', 0)
    posts = data.get('posts', 0)
    bio = data.get('biography', '')
    verified = data.get('is_verified', False)
    private = data.get('is_private', False)

    # Following too many people
    if following > 5000:
        risk += 25
        reasons.append('Following too many accounts')

    # Very low posts
    if posts <= 1:
        risk += 15
        reasons.append('Very low posts count')

    # Suspicious ratio
    if following > followers * 5 and followers > 0:
        risk += 20
        reasons.append('Suspicious follower/following ratio')

    # Empty bio
    if len(bio.strip()) == 0:
        risk += 5
        reasons.append('No bio')

    # Private accounts slightly safer
    if private:
        risk -= 5

    # Verified safer
    if verified:
        risk -= 20

    # Clamp values
    risk = max(0, min(risk, 100))

    # Status label
    if risk <= 20:
        status = 'LOW RISK 🟢'
    elif risk <= 50:
        status = 'MEDIUM RISK 🟡'
    else:
        status = 'HIGH RISK 🔴'

    return {
        'risk': risk,
        'status': status,
        'reasons': reasons
    }

# ============================================================
# ALERT SYSTEM
# ============================================================

async def send_instant_alert(username, alert_type, details):
    try:
        channel = bot.get_channel(ALERT_CHANNEL_ID)

        if not channel:
            return

        emoji_map = {
            'follower_up': '📈',
            'follower_down': '📉',
            'post_added': '📸',
            'name_changed': '📛',
            'bio_changed': '📝',
            'verified': '✅',
            'unverified': '❌',
            'private': '🔒',
            'public': '🔓',
            'banned': '🚫',
            'unbanned': '🎉'
        }

        emoji = emoji_map.get(alert_type, '🔔')

        embed = discord.Embed(
            title=f"{emoji} Instant Alert",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Account", value=f"@{username}", inline=False)

        if alert_type == 'follower_up':
            embed.description = f"Followers increased: `{details['old']}` → `{details['new']}`"

        elif alert_type == 'follower_down':
            embed.description = f"Followers decreased: `{details['old']}` → `{details['new']}`"

        elif alert_type == 'post_added':
            embed.description = f"New post detected! `{details['old']}` → `{details['new']}`"

        elif alert_type == 'verified':
            embed.description = "Account got verified ✅"

        elif alert_type == 'unverified':
            embed.description = "Verification removed ❌"

        elif alert_type == 'private':
            embed.description = "Account went private 🔒"

        elif alert_type == 'public':
            embed.description = "Account went public 🔓"

        elif alert_type == 'banned':
            embed.description = "Account appears banned 🚫"

        elif alert_type == 'unbanned':
            embed.description = "Account is back online 🎉"

        await channel.send(embed=embed)

        if username not in alert_history:
            alert_history[username] = []

        alert_history[username].append({
            'type': alert_type,
            'time': datetime.now().strftime('%H:%M:%S')
        })

    except Exception as e:
        print(e)

# ============================================================
# MONITOR SYSTEM
# ============================================================

async def monitor_account_fast(username, mode='normal', monitor_type='normal'):
    print(f"Monitoring @{username}")

    check_interval = CHECK_INTERVALS.get(mode, 60)
    last_data = None

    while True:
        try:
            if username not in tracked_accounts:
                break

            current_data = await fetch_instagram_data(username)

            if not current_data.get('success', False):
                if monitor_type == 'ban' and last_data:
                    await send_instant_alert(username, 'banned', {})
                    del tracked_accounts[username]
                    break

            elif last_data:

                if current_data['followers'] != last_data['followers']:
                    change = current_data['followers'] - last_data['followers']

                    if change > 0:
                        await send_instant_alert(username, 'follower_up', {
                            'old': last_data['followers'],
                            'new': current_data['followers']
                        })
                    else:
                        await send_instant_alert(username, 'follower_down', {
                            'old': last_data['followers'],
                            'new': current_data['followers']
                        })

                if current_data['posts'] != last_data['posts']:
                    await send_instant_alert(username, 'post_added', {
                        'old': last_data['posts'],
                        'new': current_data['posts']
                    })

                if current_data['is_verified'] != last_data['is_verified']:
                    if current_data['is_verified']:
                        await send_instant_alert(username, 'verified', {})
                    else:
                        await send_instant_alert(username, 'unverified', {})

                if current_data['is_private'] != last_data['is_private']:
                    if current_data['is_private']:
                        await send_instant_alert(username, 'private', {})
                    else:
                        await send_instant_alert(username, 'public', {})

            last_data = current_data if current_data['success'] else None

            tracked_accounts[username] = current_data

            await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            break

        except Exception as e:
            print(f"Monitor Error: {e}")
            await asyncio.sleep(5)

# ============================================================
# BOT EVENTS
# ============================================================

@bot.event
async def on_ready():
    admins.add(OWNER_ID)
    print('=' * 50)
    print(f'Logged in as {bot.user}')
    print('Dev: TanmayPlugs')
    print('=' * 50)

# ============================================================
# OWNER + ADMIN SYSTEM
# ============================================================

def is_owner(user_id):
    return user_id == OWNER_ID

def is_admin(user_id):
    return user_id in admins or user_id == OWNER_ID

# ============================================================
# COMMANDS
# ============================================================

@bot.command()
async def addadmin(ctx, user_id: int):

    if not is_owner(ctx.author.id):
        return await ctx.send("❌ Only owner can add admins")

    admins.add(user_id)

    await ctx.send(f"✅ Added `{user_id}` as admin")

@bot.command()
async def removeadmin(ctx, user_id: int):

    if not is_owner(ctx.author.id):
        return await ctx.send("❌ Only owner can remove admins")

    if user_id in admins:
        admins.remove(user_id)

    await ctx.send(f"🗑 Removed `{user_id}` from admins")

@bot.command()
async def adminslist(ctx):

    if not is_owner(ctx.author.id):
        return await ctx.send("❌ Only owner can view admins")

    text = "👑 **Bot Admins**

"

    for admin in admins:
        text += f"• `{admin}`
"

    await ctx.send(text)

@bot.command()
async def monitor(ctx, username):

    if not is_admin(ctx.author.id):
        return await ctx.send("❌ You are not bot admin")

    username = username.lstrip('@').lower()

    if username in tracked_accounts:
        return await ctx.send(f"✅ @{username} already monitored")

    msg = await ctx.send(f"⚡ Starting monitor for @{username}...")

    data = await fetch_instagram_data(username)

    if not data.get('success'):
        return await msg.edit(content="❌ Failed to fetch account")

    tracked_accounts[username] = data

    task = asyncio.create_task(
        monitor_account_fast(username, 'fast', 'normal')
    )

    monitoring_tasks[username] = task

    embed = discord.Embed(
        title="Instagram Monitoring Started",
        color=discord.Color.green()
    )

    embed.add_field(name="Username", value=f"@{username}", inline=False)
    embed.add_field(name="Followers", value=f"{data['followers']:,}")
    embed.add_field(name="Following", value=f"{data['following']:,}")
    embed.add_field(name="Posts", value=f"{data['posts']:,}")
    embed.add_field(name="Verified", value="Yes" if data['is_verified'] else "No")
    embed.add_field(name="Private", value="Yes" if data['is_private'] else "No")

    # Ban Risk Analysis
    risk_data = calculate_ban_risk(data)

    embed.add_field(
        name="Ban Risk",
        value=f"{risk_data['risk']}% - {risk_data['status']}",
        inline=False
    )

    if risk_data['reasons']:
        embed.add_field(
            name="Risk Reasons",
            value='
'.join([f'• {x}' for x in risk_data['reasons'][:5]]),
            inline=False
        )

    await msg.edit(content='', embed=embed)

@bot.command()
async def monitorban(ctx, username):

    if not is_admin(ctx.author.id):
        return await ctx.send("❌ You are not bot admin")

    username = username.lstrip('@').lower()

    tracked_accounts[username] = {
        'ban_monitor': True
    }

    task = asyncio.create_task(
        monitor_account_fast(username, 'ultra', 'ban')
    )

    monitoring_tasks[username] = task

    await ctx.send(f"🚫 Ban monitoring started for @{username}")

@bot.command()
async def stop(ctx, username):

    if not is_admin(ctx.author.id):
        return await ctx.send("❌ You are not bot admin")

    username = username.lstrip('@').lower()

    if username in monitoring_tasks:
        monitoring_tasks[username].cancel()
        del monitoring_tasks[username]

    if username in tracked_accounts:
        del tracked_accounts[username]

    await ctx.send(f"🛑 Stopped monitoring @{username}")

@bot.command()
async def list(ctx):

    if not tracked_accounts:
        return await ctx.send("📭 No accounts monitored")

    text = "📋 **Tracked Accounts**\n\n"

    for user in tracked_accounts:
        text += f"• @{user}\n"

    await ctx.send(text)

@bot.command()
async def stats(ctx):

    embed = discord.Embed(
        title="Bot Statistics",
        color=discord.Color.blurple()
    )

    embed.add_field(name="Tracked Accounts", value=len(tracked_accounts))
    embed.add_field(name="Monitoring Tasks", value=len(monitoring_tasks))
    embed.add_field(name="Alerts", value=sum(len(v) for v in alert_history.values()))
    embed.set_footer(text="Dev: TanmayPlugs")

    await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):

    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.command()
async def helpme(ctx):

    embed = discord.Embed(
        title="Instagram Monitor Commands",
        description="Dev: TanmayPlugs",
        color=discord.Color.orange()
    )

    embed.add_field(name="!monitor username", value="Start monitoring", inline=False)
    embed.add_field(name="!monitorban username", value="Ban monitor", inline=False)
    embed.add_field(name="!stop username", value="Stop monitoring", inline=False)
    embed.add_field(name="!list", value="Tracked accounts", inline=False)
    embed.add_field(name="!stats", value="Bot stats", inline=False)
    embed.add_field(name="!ping", value="Bot ping", inline=False)

    await ctx.send(embed=embed)

# ============================================================
# RUN BOT
# ============================================================

bot.run(TOKEN)
