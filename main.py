import discord
import sqlite3
import yt_dlp
import asyncio
import time
from datetime import datetime, date, timedelta

db = sqlite3.connect("fukurou.db")
cursor = db.cursor()

active_timers = {}

cursor.execute("""CREATE TABLE IF NOT EXISTS todo (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,task TEXT,completed INTEGER)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS stats(user_id INTEGER PRIMARY KEY, level INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, focus_time INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, daily_limit INTEGER DEFAULT 5, last_reset TEXT)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS timer(user_id INTEGER PRIMARY KEY, time INTEGER DEFAULT 0, timer_type TEXT)""")
db.commit()

#CHECK NEW USER

def checkUser(user_id):
    cursor.execute("SELECT user_id FROM stats WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if user is None:
        cursor.execute(
            "INSERT INTO stats (user_id) VALUES (?)",
            (user_id,)
        )
        db.commit()

#LEVELING SYSTEM

def addEXP(amount, user_id):
    cursor.execute("""UPDATE stats SET xp = xp + ? WHERE user_id = ?""", (amount, user_id))
    db.commit()
    cursor.execute("SELECT level, xp FROM stats WHERE user_id = ?", (user_id,))
    level, xp = cursor.fetchone()

    while True:
        requiredXp = 1000 + (150 * level)
        if xp < requiredXp:
            cursor.execute("UPDATE stats SET xp = ?, level = ? WHERE user_id = ?",(xp, level, user_id))
            db.commit()
            break

        xp -= requiredXp
        level += 1

#TIMER

async def countdown(user_id, seconds, timer_type, channel, user):

    total_seconds = seconds

    try:
        while seconds > 0:

            cursor.execute(
                "INSERT OR REPLACE INTO timer(user_id, time, timer_type) VALUES (?, ?, ?)",
                (user_id, seconds, timer_type)
            )
            db.commit()

            await asyncio.sleep(1)

            seconds -= 1


        cursor.execute(
            "DELETE FROM timer WHERE user_id = ?",
            (user_id,)
        )
        db.commit()

        addEXP((round(total_seconds/60)*10), user_id)

        cursor.execute(
            """
            UPDATE stats
            SET focus_time = focus_time + ?
            WHERE user_id = ?
            """,
            (round(total_seconds/60), user_id)
        )
        db.commit()

        await channel.send(
            f"⏰ {user} **Your {timer_type} session has ended!**\n"
            f"[+{round(total_seconds/60)*10}exp]"
        )

    except asyncio.CancelledError:
        cursor.execute(
            "DELETE FROM timer WHERE user_id = ?",
            (user_id,)
        )
        db.commit()
        raise

    finally:
        if user_id in active_timers:
            del active_timers[user_id]

async def stopwatch(user_id, timer_type):

    seconds = 0

    try:
        while True:
            cursor.execute(
                "INSERT OR REPLACE INTO timer(user_id, time, timer_type) VALUES (?, ?, ?)",
                (user_id, seconds, timer_type)
            )
            db.commit()

            await asyncio.sleep(1)

            seconds += 1

    except asyncio.CancelledError:
        cursor.execute(
            "DELETE FROM timer WHERE user_id = ?",
            (user_id,)
        )
        db.commit()
        raise

    finally:
        if user_id in active_timers:
            del active_timers[user_id]

class Client(discord.Client):
    async def on_ready(self):
        print(f"{self.user} is ready!")

        await self.change_presence(
            activity=discord.Game(name="fuku!help")
        )   

    async def on_message(self, message):
        #MESSAGE PARTS
        msgParts = message.content.split()

        #STUFF
        helpEmbed = discord.Embed(title= "Fukurou", description="list of all commands", color=discord.Colour.dark_blue())
        todoEmbed = discord.Embed(title= f"{message.author.display_name}'s To-do List", description=None , color=discord.Colour.orange())

        if message.author == self.user:
            return

        user_id = message.author.id
        checkUser(user_id)
        
        if message.content == "fuku!help":
            helpEmbed.add_field(name= "fuku!todo", value= "View your to-do list", inline= False)
            helpEmbed.add_field(name= "fuku! + [Task Name]", value= "Add task to your to-do list", inline= False)
            helpEmbed.add_field(name= "fuku! - [Task Name]", value= "Complete task from your to-do list", inline= False)
            helpEmbed.add_field(name= "fuku!focus", value= "Start a countdown timer", inline= False)
            helpEmbed.add_field(name= "fuku!sw", value= "Start a stopwatch", inline= False)
            helpEmbed.add_field(name= "fuku!time", value= "Check status of your timer", inline= False)
            helpEmbed.add_field(name= "fuku!timer stop", value= "Stop your timer", inline= False)
            helpEmbed.add_field(name= "fuku!lofi", value= "Play LoFi Musics", inline= False)
            await message.channel.send(embed=helpEmbed)

        elif message.content == "fuku!p":
            user_id = message.author.id

            cursor.execute("SELECT level, xp, focus_time, streak FROM stats WHERE user_id = ?", (user_id,))
            level, xp, focustime, streak = cursor.fetchone()

            profileEmbed = discord.Embed(title= f"{message.author.display_name}'s Profile", description=None, color=discord.Colour.random())
            profileEmbed.add_field(name=f"👾 Level: {level}", value="", inline=True)
            profileEmbed.add_field(name=f"⭐ Exp: {xp}/{1000+(150*level)}", value="", inline=True)
            profileEmbed.add_field(name=f"🕑 Total Time Focused: {focustime} minutes", value="", inline=True)
            profileEmbed.add_field(name=f"🔥 {streak}x Streak", value="", inline=True)

            await message.channel.send(embed=profileEmbed)

        elif message.content == "fuku!todo":
            user_id = message.author.id

            cursor.execute("SELECT task FROM todo WHERE user_id = ?", (user_id,))
            todos = cursor.fetchall()

            if len(todos) == 0:
                todoEmbed.description = "No task yet"

            for todo in todos:
                todoEmbed.add_field(name=f"⏹️ {todo[0]}", value="", inline=False)

            await message.channel.send(embed=todoEmbed)

        elif len(msgParts) >= 3 and msgParts[0] == "fuku!todo" and msgParts[1] == "+":
            tasktxt = " ".join(msgParts[2:])
            user_id = message.author.id

            cursor.execute("SELECT task FROM todo WHERE user_id = ?",(user_id,))

            todos = cursor.fetchall()
            
            cursor.execute("""INSERT INTO todo (user_id, task, completed)VALUES (?, ?, ?)""",(user_id, tasktxt, 0))
            db.commit()
            await message.channel.send(f"**Added: {tasktxt}!**")

        elif len(msgParts) >= 3 and msgParts[0] == "fuku!todo" and msgParts[1] == "-":
            user_id = message.author.id
            tasktxt = " ".join(msgParts[2:])

            cursor.execute("DELETE FROM todo WHERE user_id = ? AND task = ?", (user_id, tasktxt))

            if cursor.rowcount == 0:
                await message.channel.send("**Task doesn't exist!**")
                return

            db.commit()

            today = date.today()
            cursor.execute("SELECT daily_limit, last_reset, streak FROM stats WHERE user_id = ?", (user_id,))
            daily_limit, last_reset, streak = cursor.fetchone()

            if last_reset is not None:
                last_reset = date.fromisoformat(last_reset)
                if last_reset < today - timedelta(days=1):
                    cursor.execute("UPDATE stats SET streak = 0 WHERE user_id = ?", (user_id,))
                    db.commit()

            if last_reset != today:
                cursor.execute("UPDATE stats SET streak = streak + 1 WHERE user_id = ?", (user_id,))
                db.commit()
                daily_limit = 5
                cursor.execute("UPDATE stats SET daily_limit = ?, last_reset = ? WHERE user_id = ?", (daily_limit, str(today), user_id))
                db.commit()

            if daily_limit <= 0:
                await message.channel.send(f"**Task completed: {tasktxt} [+0 exp (daily limit reached)]**")
            elif daily_limit > 0 and daily_limit <= 5:
                daily_limit -= 1
                cursor.execute("UPDATE stats SET daily_limit = ?, last_reset = ? WHERE user_id = ?", (daily_limit, str(today), user_id))
                db.commit()
                addEXP(250, message.author.id)
                await message.channel.send(f"**Task completed: {tasktxt} [+250 exp]**")

        elif message.content == "fuku!todo clear":
            user_id = message.author.id

            cursor.execute("DELETE FROM todo WHERE user_id = ?",(user_id,))

            db.commit()

            await message.channel.send("Cleared all tasks!") 

        elif len(msgParts) >= 2 and msgParts[0] == "fuku!focus":

            user = message.author.mention

            try:
                time = int(msgParts[1])
            except ValueError:
                await message.channel.send(
                    "**❌Unable to set timer: time must be a number**"
                )
                return


            cursor.execute(
                "SELECT * FROM timer WHERE user_id = ?",
                (user_id,)
            )

            if cursor.fetchone():
                await message.channel.send(
                    "**You already have a timer running!**"
                )
                return


            await message.channel.send(
                f"⏳ **{time} minutes focus session has started!**\n"
                f"**use [fuku!time] to check remaining time**"
            )


            task = asyncio.create_task(
                countdown(
                    user_id,
                    time*60,
                    "Focus",
                    message.channel,
                    user
                )
            )

            active_timers[user_id] = task

        elif message.content == "fuku!time":

            cursor.execute(
                "SELECT time, timer_type FROM timer WHERE user_id = ?",
                (user_id,)
            )

            timer = cursor.fetchone()

            if timer is None:
                await message.channel.send(
                    "❌ You don't have an active timer."
                )
                return

            seconds, timer_type = timer

            minutes = seconds // 60
            seconds_left = seconds % 60

            embed = discord.Embed(
                title="⏳ Timer Status",
                color=discord.Color.orange()
            )

            if timer_type == "Stopwatch":
                embed.add_field(
                    name="Elapsed Time:",
                    value=f"{minutes}m {seconds_left}s",
                    inline=False
                )
                embed.add_field(
                    name="Accumulated EXP:",
                    value=f"{10*minutes}",
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"{timer_type} Remaining:",
                    value=f"{minutes}m {seconds_left}s",
                    inline=False
                )

            await message.channel.send(embed=embed)

        elif message.content == "fuku!timer stop":

            if user_id not in active_timers:
                await message.channel.send("❌ You don't have an active timer.")
                return

            # Get elapsed time BEFORE deleting
            cursor.execute(
                "SELECT time, timer_type FROM timer WHERE user_id = ?",
                (user_id,)
            )
            timer = cursor.fetchone()

            active_timers[user_id].cancel()

            if timer:
                seconds, timer_type = timer
                total_seconds = seconds

                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                seconds = seconds % 60

                cursor.execute(
                    """
                    UPDATE stats
                    SET focus_time = focus_time + ?
                    WHERE user_id = ?
                    """,
                    (round(total_seconds/60), user_id)
                )
                db.commit()

                addEXP((round(total_seconds / 60)*10), message.author.id)

                await message.channel.send(
                    f"🛑 {timer_type} stopped.\n"
                    f"⏱️ Total time: **{hours:02}:{minutes:02}:{seconds:02}**\n"
                    f"[+{(round(total_seconds / 60)*10)}exp]"
                )

            cursor.execute(
                "DELETE FROM timer WHERE user_id = ?",
                (user_id,)
            )
            db.commit()

            del active_timers[user_id]

        elif message.content == "fuku!sw":

            if user_id in active_timers:
                await message.channel.send(
                    "⏱️ You already have a timer running!"
                )
                return


            await message.channel.send(
                "⏱️ Stopwatch started!"
            )


            task = asyncio.create_task(
                stopwatch(
                    user_id,
                    "Stopwatch"
                )
            )

            active_timers[user_id] = task

        elif message.content == "fuku!lofi":
            if message.author.voice:
                channel = message.author.voice.channel

                voice = message.guild.voice_client

                if voice is None:
                    voice = await channel.connect()

                ydl_opts = {
                    "format": "bestaudio/best",
                    "quiet": True,
                    "noplaylist": True,
                    "js_runtimes": {
                        "deno": {}
                    }
                }

                url = "https://www.youtube.com/watch?v=UJs6__K7gSY"

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                audio_url = info["url"]

                source = discord.FFmpegPCMAudio(audio_url)

                voice.play(source, after=lambda e: voice.play(discord.FFmpegPCMAudio(audio_url))
)
                await message.channel.send("**🎵 Playing lofi!**")

            else:
                await message.channel.send("**You need to join a voice channel to start playing music!**")
        elif message.content == "fuku!stop":
                voice = message.guild.voice_client

                if voice is None:
                    await message.channel.send("**I'm not in a voice channel**")
                    return

                await voice.disconnect()
                await message.channel.send("**Left the voice channel!**")

#Intents Setup
intents = discord.Intents.default()
intents.message_content = True
client = Client(command_prefix="!", intents=intents)

client.run('MTUzNDgzNzEyMTU2OTc4ODAwNQ.GsgBe8.neoNIy_q7hAAOnmKpUEvij59FyLADOSPYpyYUw')
