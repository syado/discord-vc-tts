import discord
from discord import opus
import requests
import asyncio
from functools import wraps
import datetime
import os
import json
import re
import base64
import threading
from gtts import gTTS
import uuid

f = open("config.json", encoding='utf-8')
config = json.load(f)
f.close()
token = config["discord"]["token"]

opus_libs = ['libopus-0.x86.dll', 'libopus-0.x64.dll', 'libopus-0.dll', 'libopus.so.0', 'libopus.0.dylib', 'libopus.so.1']

for opus_lib in opus_libs:  # VCを使ううえで必要なファイルを読み込む
    try:
        opus.load_opus(opus_lib)
        print("opus load")
    except OSError:
        pass

playlist = {}

"""
{
    serverid1: [[ストリーム0,fname0],[ストリーム1,fname1]]
    serverid2: [[ストリーム0,fname0],[ストリーム1,fname1],[ストリーム2,fname2]]
}
＊ストリーム: create_ffmpeg_player(fname)
"""

play_flag = []
yomi_user = []  # UserIDがあるものは読み上げオン
yomi_channel = []  # ChannelIDがあるものは読み上げオン
time = {}

client = discord.Client()

def echo(func):
    @wraps(func)
    async def wrapper(message):
        dt = datetime.datetime.today().strftime("%Y-%m-%d %H:%M:%S")
        print(dt+" "+message.content)
        await func(message)
    return wrapper

def message_author_voice_channel(func):
    @wraps(func)
    async def wrapper(message):
        if message.author.voice_channel:  # コマンド入力者が音声チャンネルに存在しているか
            return await func(message)
        else:
            m = ":no_entry_sign: あなたはボイスチャンネルに接続していません"
            return await client.send_message(message.channel, m)
    return wrapper

def client_is_voice_connected(func):
    @wraps(func)
    async def wrapper(message):
        if client.is_voice_connected(message.server):  # botが音声チャンネルに接続されているか
            return await func(message)
        else:
            m = ":no_entry_sign: わたしはボイスチャンネルに接続していません"
            return await client.send_message(message.channel, m)
    return wrapper

def vcwrite(message):
    fname = "./"+"vcfile"+"/"+str(uuid.uuid4())+".wav"
    messagestr = message.content
    messagestr = re.sub(r"https?://[\w/:%#\$&\?\(\)~\.=\+\-]+", "、以下URL省略、", messagestr)
    messagestr = re.sub(r"`+[\S\s]+`+", "、以下省略、", messagestr)
    while True:
        m = re.search(r"<@[0-9]+>", messagestr)
        if m:
            member = message.server.get_member(m.group()[2:-1])
            messagestr = messagestr.replace(m.group(), member.name+"さん")
        else:
            break
    while True:
        m = re.search(r"<@![0-9]+>", messagestr)
        if m:
            member = message.server.get_member(m.group()[3:-1])
            messagestr = messagestr.replace(m.group(), member.name+"さん")
        else:
            break
    # 役職名置き換え未完成
    while True:
        m = re.search(r"<@&[0-9]+>", messagestr)
        if m:
            messagestr = messagestr.replace(m.group(), "役職メンション")
        else:
            break
    while True:
        r = re.search(r"<#[0-9]+>", messagestr)
        if r:
            channel = message.server.get_channel(r.group()[2:-1])
            messagestr = messagestr.replace(r.group(), channel.name+"チャンネル")
        else:
            break
    while True:
        r = re.search(r"<:\w+:[0-9]+>", messagestr)
        if r:
            channel = message.server.get_channel(r.group()[2:-1])
            messagestr = messagestr.replace(r.group(), " ")
        else:
            break
    gTTS(text=messagestr, lang='ja').save(fname)
    return fname

def play(server):
    player = playlist[server.id]
    if player[0][0].is_done():     # 再生が終わったら
        player[0][0].stop()        # 一応再生停止
        os.remove(player[0][1])    # 音声ファイル削除
        player.pop(0)              # リストの0個目を削除
        if 0 < len(player):        # 次再生すべき物があるか
            player[0][0].start()   # 次のを再生

@echo
@message_author_voice_channel
async def join(message):
    if client.is_voice_connected(message.server):  # botが音声チャンネルに接続されているか
        vc = client.voice_client_in(message.server)  # vcをクライアント呼び出す
        m = ":no_entry_sign: すでに"+vc.channel.name+"に接続しています"
    else:
        m = ":white_check_mark: ボイスチャンネル"+message.author.voice_channel.name+"に接続しました"
        play_flag.append(message.server.id)
        # コマンド入力者のボイスチャンネルに接続
        await client.join_voice_channel(message.author.voice_channel)
        time[message.server] = int(datetime.datetime.now().timestamp())
        try:
            if 0 < len(playlist[message.server.id]):
                pass
        except:
            playlist[message.server.id] = []

    return await client.send_message(message.channel, m)

@echo
async def join_id(message):
    if client.is_voice_connected(message.server):  # botが音声チャンネルに接続されているか
        vc = client.voice_client_in(message.server)  # vcをクライアント呼び出す
        m = ":no_entry_sign: すでに"+vc.channel.name+"に接続しています"
    else:
        vc_id = message.content.split()[1]
        voice_channel = client.get_channel(vc_id)
        await client.join_voice_channel(voice_channel)
        m = ":white_check_mark: ボイスチャンネル"+voice_channel.name+"に接続しました"
        play_flag.append(message.server.id)
        # コマンド入力者のボイスチャンネルに接続
        time[message.server] = int(datetime.datetime.now().timestamp())
        try:
            if 0 < len(playlist[message.server.id]):
                pass
        except:
            playlist[message.server.id] = []

    return await client.send_message(message.channel, m)

@echo
@message_author_voice_channel
@client_is_voice_connected
async def disconect(message):
    # 接続されている場合
    vc = client.voice_client_in(message.server)  # vcのクライアント呼び出す
    if vc.channel == message.author.voice_channel:  # コマンド入力者のいるチャンネルとbotのいるチャンネルが同じか
        # 同じ場合
        await vc.disconnect()  # vcを切断
        play_flag.remove(message.server.id)
        del time[message.server]
        m = ":white_check_mark: ボイスチャンネル"+vc.channel.name+"から切断しました"

    else:
        # 違う場合
        m = ":no_entry_sign: あなたはわたしのいるボイスチャンネルに接続していません"
    return await client.send_message(message.channel, m)

@echo
@message_author_voice_channel
@client_is_voice_connected
async def reconect(message):
    # 接続されている場合
    vc = client.voice_client_in(message.server)  # vcのクライアント呼び出す
    if vc.channel == message.author.voice_channel:  # コマンド入力者のいるチャンネルとbotのいるチャンネルが同じか
        # 同じ場合
        await vc.disconnect()  # vcを切断
        await client.join_voice_channel(vc.channel)
        time[message.server] = int(datetime.datetime.now().timestamp())
        m = ":white_check_mark: ボイスチャンネル"+vc.channel.name+"に再接続しました"

    else:
        # 違う場合
        m = ":no_entry_sign: あなたはわたしのいるボイスチャンネルに接続していません"
    return await client.send_message(message.channel, m)

@echo
@message_author_voice_channel
@client_is_voice_connected
async def move(message):
    # 接続されている場合
    vc = client.voice_client_in(message.server)  # vcのクライアント呼び出す
    await vc.move_to(message.author.voice_channel)  # コマンド入力者のボイスチャンネルに移動接続
    time[message.server] = int(datetime.datetime.now().timestamp())
    m = ":white_check_mark: ボイスチャンネル"+vc.channel.name + \
        "から"+message.author.voice_channel.name+"に移動しました"
    return await client.send_message(message.channel, m)

@echo
async def yomi(message):
    messagelist = message.content.split()
    if len(messagelist) < 3:
        m = 'ユーザーの読み上げ設定は ``yomi user on|off`` です\n'
        m += 'チャンネルの読み上げ設定は ``yomi ch on|off`` です'
        return await client.send_message(message.channel, m)

    elif messagelist[1].lower() == "user":
        if messagelist[2].lower() == "on":
            if not message.author.id in yomi_user:
                yomi_user.append(message.author.id)
                m = '<@{0}> のメッセージを読み上げする設定にしました'.format(message.author.id)
            else:
                m = 'すでに<@{0}> のメッセージを読み上げする設定です'.format(message.author.id)

        elif messagelist[2].lower() == "off":
            if message.author.id in yomi_user:
                yomi_user.remove(message.author.id)
                m = '<@{0}> のメッセージを読み上げしない設定にしました'.format(message.author.id)
            else:
                m = 'すでに<@{0}> のメッセージを読み上げしない設定です'.format(message.author.id)

        else:
            m = '正しいコマンドは ``yomi user on|off`` です'
            return await client.send_message(message.channel, m)

        with open("yomi_user.txt", "w") as f:
            f.write("\n".join(yomi_user))
        f.close()
        return await client.send_message(message.channel, m)

    elif messagelist[1].lower() == "ch":
        if messagelist[2].lower() == "on":
            if not message.channel.id in yomi_channel:
                yomi_channel.append(message.channel.id)
                m = '<#{0}> のメッセージを読み上げする設定にしました'.format(message.channel.id)
            else:
                m = 'すでに<#{0}> のメッセージを読み上げする設定です'.format(message.channel.id)

        elif messagelist[2].lower() == "off":
            if message.channel.id in yomi_channel:
                yomi_channel.remove(message.channel.id)
                m = '<#{0}> のメッセージを読み上げしない設定にしました'.format(message.channel.id)
            else:
                m = 'すでに<#{0}> のメッセージを読み上げしない設定です'.format(message.channel.id)

        else:
            m = '正しいコマンドは ``yomi ch on|off`` です'
            return await client.send_message(message.channel, m)
            
        with open("yomi_channel.txt", "w") as f:
            f.write("\n".join(yomi_channel))
        f.close()
        return await client.send_message(message.channel, m)

    else:
        m = 'ユーザーの読み上げ設定は ``yomi user on|off`` です\n'
        m += 'チャンネルの読み上げ設定は ``yomi ch on|off`` です'
        return await client.send_message(message.channel, m)
        
@echo
async def cmd_help(message):
    m = "```\n"
    m += "join, summon      : vcに接続\n"
    m += "dc, disconnect    : vcから切断\n"
    m += "rc, reconnect     : vcに再接続\n"
    m += "move              : vc1からvc2に移動\n"
    m += "yomi user on|off  : ユーザーの読み上げ設定\n"
    m += "yomi ch on|off    : チャンネルの読み上げ設定\n"
    m += "```"
    return await client.send_message(message.channel, m)

@echo
async def tts(message):
    if client.is_voice_connected(message.server):  # botが音声チャンネルに接続されているか
        vc = client.voice_client_in(message.server)  # vcのクライアント呼び出す
        if time[message.server] + 3600 < int(datetime.datetime.now().timestamp()):
            await vc.disconnect()  # vcを切断
            vc = await client.join_voice_channel(vc.channel)
            time[message.server] = int(datetime.datetime.now().timestamp())
        fname = vcwrite(message)  # 音声合成ファイル作成　戻り値はファイルディレクトリ
        cfp = vc.create_ffmpeg_player(fname,after=lambda: play(message.server))  # ストリーム作成
        tmp = [cfp, fname]  # ストリーム, ファイルディレクトリをリスト化
        playlist[message.server.id].append(tmp)  # サーバーごとの辞書にリストを追加
        if 1 == len(playlist[message.server.id]):  # 再生中のものがない場合
            playlist[message.server.id][0][0].start()

@client.event
async def on_ready():
    f = open("yomi_user.txt", "r")
    for line in f:
        yomi_user.append(line.replace('\n',''))
    f.close()
    f = open("yomi_channel.txt", "r")
    for line in f:
        yomi_channel.append(line.replace('\n',''))
    f.close()

    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

@client.event
async def on_message(message):
    messagelist = message.content.split()
    if len(messagelist) > 0:
        cmd_str = messagelist[0].lower()
        if cmd_str in {"join", "summon"}:  # 音声チャンネル接続
            if len(messagelist) == 2:
                return await join_id(message)
            else:
                return await join(message)
        elif cmd_str in {"dc", "disconnect"}:  # 音声チャンネル切断
            return await disconect(message)
        elif cmd_str in {"move"}:  # 音声チャンネル移動
            return await move(message)
        elif cmd_str in {"rc", "reconnect"}:  # 音声チャンネル再接続
            return await reconect(message)
        elif cmd_str in {"yomi"}:  # 読み上げ設定
            return await yomi(message)
        elif cmd_str in {"help"}:  # 読み上げ設定
            return await cmd_help(message)
        elif message.author.id != client.user.id:
            if message.channel.id in yomi_channel:
                if message.author.id in yomi_user:
                    if not message.content.startswith(")"):
                        return await tts(message)

if __name__ == "__main__":
    client.run(token) 