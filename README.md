# play_zonk_bot
This is a Telegram bot that hosts multiplayer Zonk (Farkle) games in group chats.
A live instance of the bot is available here: https://t.me/play_zonk_bot. Feel free to play!

## Installation
If you don't want to use the available instance, you can set up your own bot. The only prerequisites are Python 3.9+ and an Internet connection, and the only dependency is `python-telegram-bot` package (https://github.com/python-telegram-bot/python-telegram-bot).
1. Ensure that Python 3.9+ is installed on your computer
2. Register your bot using BotFather (https://t.me/BotFather) and obtain a token.
3. Clone this repository to your computer or server:
```
git clone https://github.com/a17sol/play_zonk_bot.git
```
4. Install dependencies: 
```
pip install -r requirements.txt
```
5. Create a startup script, that sets an environment variable `ZONK_TOKEN` with the token you received from BotFather, then runs `main.py`.
6. Run your script. Send `/start` to your bot and enjoy!

## Usage
While single-player games in a personal chat with the bot are possible, the main purpose of the bot is to facilitate multiplayer games between friends or colleagues. Simply add the bot to your favorite chat and send one of the game commands. `/zonk` or `/zonk_b` (see below) will post an invitation that any number of users in the chat can accept. When the initiator is satisfied with the player lineup, they can start the game by pressing the corresponding button. They can also cancel the game before it starts. Invitations expire and are deleted after 15 minutes.

The game process is intuitive and follows the standard Zonk (Farkle) rules: players roll their dice, select combos using the poll interface, and decide when to stop by pressing the corresponding button. Players have 15 minutes to complete their turn; otherwise, they will be kicked out. At the end of the game, a leaderboard is displayed.

## Command List
- `/start` - Welcome message
- `/help` - Help and info
- `/rules` - Game rules
- `/zonk` - Play Zonk (AKA Farkle, see rules for details)
- `/zonk_b` - Play Butovo Zonk (a local variation, see rules for details)
- `/leave` - Leave the game (can be used anytime during or before the game)
- `/stat` and `/ver` - Service commands, not useful for players but helpful for bot development and maintenance
