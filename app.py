import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import os
import re
from dotenv import load_dotenv
from urllib.parse import quote
import emoji
from collections import deque

load_dotenv()

VOICEVOX_BASE_URL = os.getenv('VOICEVOX_URL', 'http://localhost:50021/')
DEFAULT_VOICE = os.getenv('DEFAULT_VOICE', '6')
MAX_MESSAGE_LENGTH = int(os.getenv('MAX_MESSAGE_LENGTH', '150'))
FILE_DELETE_DELAY = int(os.getenv('FILE_DELETE_DELAY', '5'))
SOUNDS_DIR = "sounds"

os.makedirs(SOUNDS_DIR, exist_ok=True)

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

voice_map = {}
audio_queues = {}
is_playing = {}


def convert_message(text):
    text = re.sub(r'<:[a-zA-Z0-9_]+:[0-9]+>', '', text)
    text = emoji.replace_emoji(text, '')
    text = re.sub(r'(https?|ftp)(://[\w/:%#\$&\?$$$$~\.=\+\-]+)', '', text)
    text = text.replace('\n', '、').replace('\r', '')
    
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH] + '、以下略'
    
    return text


async def generate_audio(text, filepath, voice):
    try:
        async with aiohttp.ClientSession() as session:
            audio_query_url = f"{VOICEVOX_BASE_URL}audio_query?text={quote(text)}&speaker={voice}"
            async with session.post(audio_query_url, headers={'accept': 'application/json'}) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"audio_query failed: {response.status} - {error_text}")
                audio_query = await response.json()
            
            synthesis_url = f"{VOICEVOX_BASE_URL}synthesis?speaker={voice}"
            async with session.post(
                synthesis_url,
                json=audio_query,
                headers={
                    "accept": "audio/wav",
                    "Content-Type": "application/json"
                }
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"synthesis failed: {response.status} - {error_text}")
                audio_data = await response.read()
            
            with open(filepath, 'wb') as f:
                f.write(audio_data)
    except aiohttp.ClientConnectorError as e:
        print(f"VOICEVOXエンジンに接続できません: {e}")
        raise
    except Exception as e:
        print(f"音声生成エラー: {e}")
        raise


async def delete_audio_file(filepath, delay):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"ファイル削除エラー: {e}")


async def process_audio_queue(guild_id):
    while True:
        if guild_id not in audio_queues or len(audio_queues[guild_id]) == 0:
            is_playing[guild_id] = False
            await asyncio.sleep(0.5)
            continue
        
        is_playing[guild_id] = True
        
        audio_data = audio_queues[guild_id].popleft()
        voice_client = audio_data['voice_client']
        filepath = audio_data['filepath']
        
        if not voice_client or not voice_client.is_connected():
            continue
        
        try:
            play_finished = asyncio.Event()
            
            def after_playing(error):
                if error:
                    print(f"再生エラー: {error}")
                bot.loop.create_task(delete_audio_file(filepath, FILE_DELETE_DELAY))
                play_finished.set()
            
            audio_source = discord.FFmpegPCMAudio(filepath)
            voice_client.play(audio_source, after=after_playing)
            
            await play_finished.wait()
            await asyncio.sleep(0.3)
            
        except Exception as e:
            print(f"音声再生エラー: {e}")
            bot.loop.create_task(delete_audio_file(filepath, FILE_DELETE_DELAY))


async def add_to_queue(message, filepath):
    guild_id = message.guild.id
    
    if not message.author.voice:
        return
    
    voice_channel = message.author.voice.channel
    
    if not voice_channel.permissions_for(message.guild.me).connect:
        return
    
    if not voice_channel.permissions_for(message.guild.me).speak:
        return
    
    voice_client = message.guild.voice_client
    
    if not voice_client:
        try:
            voice_client = await voice_channel.connect(self_deaf=True)
        except Exception as e:
            print(f"VC接続エラー: {e}")
            return
    
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)
    
    if guild_id not in audio_queues:
        audio_queues[guild_id] = deque()
        is_playing[guild_id] = False
        asyncio.create_task(process_audio_queue(guild_id))
    
    audio_queues[guild_id].append({
        'voice_client': voice_client,
        'filepath': filepath
    })


@bot.event
async def on_ready():
    print(f'{bot.user} としてログインしました')
    print(f"VOICEVOXエンジンURL: {VOICEVOX_BASE_URL}")
    print(f"最大文字数: {MAX_MESSAGE_LENGTH}文字")
    print(f"ファイル削除遅延: {FILE_DELETE_DELAY}秒")
    print("Ready!")
    
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)}個のコマンドを同期しました")
    except Exception as e:
        print(f"コマンド同期エラー: {e}")


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    if before.channel is not None:
        voice_client = member.guild.voice_client
        
        if voice_client and voice_client.channel == before.channel:
            members = [m for m in before.channel.members if not m.bot]
            
            if len(members) == 0:
                guild_id = member.guild.id
                
                if guild_id in audio_queues:
                    audio_queues[guild_id].clear()
                    is_playing[guild_id] = False
                
                await voice_client.disconnect()


@bot.tree.command(name="join", description="ボイスチャンネルに参加します")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message(
            "先にボイスチャンネルに参加してください",
            ephemeral=True
        )
        return
    
    voice_channel = interaction.user.voice.channel
    
    try:
        if interaction.guild.voice_client:
            if interaction.guild.voice_client.channel == voice_channel:
                await interaction.response.send_message(
                    f"既に{voice_channel.name}に参加しています",
                    ephemeral=True
                )
            else:
                await interaction.guild.voice_client.move_to(voice_channel)
                await interaction.response.send_message(
                    f"{voice_channel.name}に移動しました",
                    ephemeral=True
                )
        else:
            await voice_channel.connect(self_deaf=True)
            await interaction.response.send_message(
                f"{voice_channel.name}に参加しました",
                ephemeral=True
            )
    except Exception as e:
        print(f"エラー: {e}")
        await interaction.response.send_message(
            f"エラーが発生しました: {e}",
            ephemeral=True
        )


@bot.tree.command(name="leave", description="ボイスチャンネルから退出します")
async def leave(interaction: discord.Interaction):
    if not interaction.guild.voice_client:
        await interaction.response.send_message(
            "ボイスチャンネルに参加していません",
            ephemeral=True
        )
        return
    
    try:
        guild_id = interaction.guild.id
        
        if guild_id in audio_queues:
            audio_queues[guild_id].clear()
            is_playing[guild_id] = False
        
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message(
            "ボイスチャンネルから退出しました",
            ephemeral=True
        )
    except Exception as e:
        print(f"退出エラー: {e}")
        await interaction.response.send_message(
            f"退出時にエラーが発生しました: {e}",
            ephemeral=True
        )


@bot.tree.command(name="skip", description="現在再生中の音声をスキップします")
async def skip(interaction: discord.Interaction):
    if not interaction.guild.voice_client:
        await interaction.response.send_message(
            "ボイスチャンネルに参加していません",
            ephemeral=True
        )
        return
    
    if interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message(
            "音声をスキップしました",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "再生中の音声がありません",
            ephemeral=True
        )


@bot.tree.command(name="clear", description="音声キューをクリアします")
async def clear_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    
    if guild_id in audio_queues:
        queue_size = len(audio_queues[guild_id])
        audio_queues[guild_id].clear()
        await interaction.response.send_message(
            f"キューをクリアしました ({queue_size}件)",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "キューは空です",
            ephemeral=True
        )


@bot.tree.command(name="setvoice", description="音声の話者を設定します")
@app_commands.describe(speaker="話者ID (例: 1, 2, 3...)")
async def setvoice(interaction: discord.Interaction, speaker: str):
    voice_map[interaction.user.id] = speaker
    await interaction.response.send_message(
        f"音声を話者ID {speaker} に設定しました",
        ephemeral=True
    )


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    await bot.process_commands(message)
    
    if not message.clean_content.strip():
        return
    
    filepath = os.path.join(SOUNDS_DIR, f"{message.author.id}_{message.id}.wav")
    voice = voice_map.get(message.author.id, DEFAULT_VOICE)
    
    converted_message = convert_message(message.clean_content)
    
    if not converted_message.strip():
        return
    
    try:
        await generate_audio(converted_message, filepath, voice)
        await add_to_queue(message, filepath)
    except Exception as e:
        print(f"エラー: {e}")


if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("エラー: DISCORD_TOKENが設定されていません")
    else:
        bot.run(token)
