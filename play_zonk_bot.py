# TODO: change poll removal system
# TODO: factor out game end
# TODO: check_inactivity safety


from os import getenv
from time import time
from random import randrange, shuffle, choice
from asyncio import sleep
from collections import Counter
import logging
from traceback import extract_tb

from telegram import (
	Update, 
	InlineKeyboardButton, 
	InlineKeyboardMarkup, 
	LinkPreviewOptions
)
from telegram.ext import (
	Application,
	CommandHandler,
	CallbackQueryHandler,
	ContextTypes,
	PollAnswerHandler,
	PicklePersistence,
	CallbackContext
)
from telegram.error import TelegramError, NetworkError


logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s',
	handlers=[
		logging.FileHandler("zonk.log"),
		logging.StreamHandler()
	]
)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

token = getenv("ZONK_TOKEN")
if not token:
	logging.error("Token not set. Aborting.")
	exit()

target = 5000


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text("Привет! Я зонк-бот для групповых чатов. Добавляй меня в группы и пиши /zonk, чтобы начать игру с друзьями!\nДополнительная информация здесь: /help", disable_notification=True)


async def zonk_b(update, context):
	if context.chat_data.get("game_in_process", False):
		await update.message.reply_text("Игра уже идёт", disable_notification=True)
		return
	context.chat_data["game_type"] = "butovo"
	await play(update, context)


async def zonk(update, context):
	if context.chat_data.get("game_in_process", False):
		await update.message.reply_text("Игра уже идёт", disable_notification=True)
		return
	context.chat_data["game_type"] = "classic"
	await play(update, context)


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	title = update.message.chat.title or "(personal chat)"

	logging.info("Invite posted in chat %d \"%s\" by %s", update.message.chat.id, title, update.effective_user.full_name)
	
	user = update.effective_user
	context.chat_data["game_in_process"] = randrange(1, 1000000)
	context.chat_data["turn"] = 0
	context.chat_data["players"] = {}
	context.chat_data["initiator"] = user

	context.chat_data["board"] = await context.bot.send_message(
		chat_id=update.effective_chat.id,
		text=make_inviteboard(context),
		parse_mode="html", 
		reply_markup=make_invite_markup(context)
	)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

	query = update.callback_query
	user = query.from_user
	button_type, owner_id = query.data.split(":")

	if button_type == "join":
		if str(user.id) == owner_id or user in context.chat_data["players"]:
			await query.answer("Ты уже в списке участников")
			return
		context.chat_data["players"][user] = 0
		await query.edit_message_text(
			make_inviteboard(context),
			parse_mode="html",
			reply_markup=make_invite_markup(context)
		)

	elif str(user.id) != owner_id:
		await query.answer("Это не твоя кнопка")
		return

	elif button_type == "begin":
		context.chat_data["players"][user] = 0
		players = list(context.chat_data["players"])
		shuffle(players)
		context.chat_data["players"] = {pl : 0 for pl in players}
		context.chat_data["player_iterator"] = iter(dict(context.chat_data["players"]))
		context.chat_data["current_player"] = None
		context.chat_data["leaderboard"] = []
		context.chat_data["current_roll"] = []
		context.chat_data["selected_dices"] = set()
		context.chat_data["subtotal"] = 0
		context.chat_data["turn"] = 1
		await next_move(context)

	elif button_type == "cancel":
		context.chat_data["game_in_process"] = 0
		await query.edit_message_text("Игра отменена")

	elif button_type == "notake":
		context.application.create_task(delete_poll(context))
		await next_move(context)
		# await query.message.delete()

	elif button_type == "take&continue":
		context.application.create_task(delete_poll(context))
		scoring_func = scoring if context.chat_data["game_type"] == 'classic' else scoring_b
		subsubtotal, dices_used = scoring_func(context)
		if subsubtotal == 0:
			context.chat_data["subtotal"] = 0
			await next_move(context)
		else:
			context.chat_data["subtotal"] += subsubtotal
			dices_to_roll = len(context.chat_data["current_roll"]) - dices_used
			if dices_to_roll == 0:
				dices_to_roll = 6
			await roll(dices_to_roll, context)
		# await query.message.delete()

	elif button_type == "take&finish":
		context.application.create_task(delete_poll(context))
		scoring_func = scoring if context.chat_data["game_type"] == 'classic' else scoring_b
		subsubtotal, _ = scoring_func(context)
		if subsubtotal == 0:
			context.chat_data["subtotal"] = 0
		else:
			context.chat_data["subtotal"] += subsubtotal
		context.chat_data["players"][context.chat_data["current_player"]] += context.chat_data["subtotal"]
		player_points = context.chat_data["players"][context.chat_data["current_player"]]
		if player_points >= target:
			context.chat_data["leaderboard"].append(context.chat_data["current_player"])
			del context.chat_data["players"][context.chat_data["current_player"]]
			if len(context.chat_data["players"]) <= 1:
				context.chat_data["leaderboard"] += list(context.chat_data["players"])
				await context.chat_data["board"].delete()
				context.chat_data["board"] = await context.bot.send_message(
					chat_id=context._chat_id,
					text=make_leaderboard(context),
					parse_mode="html",
					disable_notification=True
				)
				context.chat_data["game_in_process"] = 0
				return
		await next_move(context)
		# await query.message.delete()

	await query.answer()


async def next_move(context):
	try:
		pl = context.chat_data["current_player"] = next(context.chat_data["player_iterator"])
	except StopIteration:
		context.chat_data["turn"] += 1
		context.chat_data["player_iterator"] = iter(dict(context.chat_data["players"]))
		pl = context.chat_data["current_player"] = next(context.chat_data["player_iterator"])

	context.chat_data["subtotal"] = 0
	await roll(6, context)
	context.chat_data["move_begin_time"] = time()


async def roll(dices_to_roll, context):

	tmp = await context.bot.send_message(
		chat_id=context._chat_id,
		text=make_scoreboard(context),
		parse_mode="html",
		disable_notification=True
	)
	context.chat_data["current_roll"] = [randrange(1, 7) for _ in range(dices_to_roll)]
	context.chat_data["selected_dices"] = set()
	await create_poll(context)
	await context.chat_data["board"].delete()
	context.chat_data["board"] = tmp


def make_take_markup(user_id):
	keyboard = []
	keyboard.append([InlineKeyboardButton("Забрать и продолжить", callback_data=f"take&continue:{user_id}")])
	keyboard.append([InlineKeyboardButton("Забрать и закончить", callback_data=f"take&finish:{user_id}")])
	return InlineKeyboardMarkup(keyboard)


def make_invite_markup(context):
	user = context.chat_data["initiator"]
	keyboard = [
		[InlineKeyboardButton("Я хочу!", callback_data=f"join:{user.id}")],
		[InlineKeyboardButton(f"{user.first_name}, нажми, чтобы начать", callback_data=f"begin:{user.id}")],
		[InlineKeyboardButton(f"{user.first_name}, нажми, чтобы отменить", callback_data=f"cancel:{user.id}")],
	]
	return InlineKeyboardMarkup(keyboard)


def make_inviteboard(context):
	string = context.chat_data['initiator'].mention_html() + " хочет сыграть в "
	string += "бутовский зонк" if context.chat_data['game_type'] == 'butovo' else "классический зонк"
	string += ". Кто в деле?\n"
	if context.chat_data['players']:
		players_names = [u.mention_html() for u in context.chat_data["players"]]
		string += "Отозвались:\n" + "\n".join(players_names)
	return string


def make_scoreboard(context):
	string = "Бутовский" if context.chat_data['game_type'] == 'butovo' else "Классический"
	string += " зонк\nКруг " + str(context.chat_data["turn"]) + "\n"
	string += "Текущий счёт:\n"
	for u, p in context.chat_data["players"].items():
		string += f"{u.full_name} - {p}"
		if u == context.chat_data["current_player"]:
			string += "+" + str(context.chat_data["subtotal"])
		string += "\n"
	for u in context.chat_data["leaderboard"]:
		string += f"{u.full_name} закончил(а)\n"
	#string += "\n".join([f"{u.full_name} - {p}" for u, p in context.chat_data["players"].items()]) + "\n"
	string += "Ходит " + context.chat_data["current_player"].mention_html()
	return string


def make_leaderboard(context):
	string = "Игра окончена!\n"
	for i, u in enumerate(context.chat_data["leaderboard"]):
		string += f"{i + 1} место - {u.mention_html()}" + "\n"
	return string


def scoring(context):
	values = [0, 100, 20, 30, 40, 50, 60]
	mult = [0, 0, 0, 10, 20, 40, 80]
	count = 0
	dices_used = 0
	di = context.chat_data["current_roll"]
	sel = context.chat_data["selected_dices"]
	take = [di[n] for n in sel if n < len(di)]
	take_table = Counter(take)
	if len(take_table) == 6:
		count += 1500
		dices_used += 6
	elif len(take_table) == 3 and all(i[1] == 2 for i in take_table.items()):
		count += 750
		dices_used += 6
	else:
		for points, times in take_table.items():
			if mult[times]:
				count += values[points] * mult[times]
				dices_used += times
			elif points in (1, 5):
				count += values[points] * times
				dices_used += times
	return count, dices_used


def scoring_b(context):
	values = [0, 100, 20, 30, 40, 50, 60]
	mult = [0, 0, 0, 10, 20, 40, 80]
	combos = {"123456": 1500, "23456": 750, "12345": 500}
	count = 0
	dices_used = 0
	di = context.chat_data["current_roll"]
	sel = context.chat_data["selected_dices"]
	take = [di[n] for n in sel if n < len(di)]
	take_table = Counter(take)
	for combo in combos:
		if all(int(item) in take for item in combo):
			count += combos[combo]
			dices_used += len(combo)
			for i in combo:
				take_table[int(i)] -= 1
			break
	for points, times in take_table.items():
		if mult[times]:
			count += values[points] * mult[times]
			dices_used += times
		elif points in (1, 5):
			count += values[points] * times
			dices_used += times
	return count, dices_used


async def poll_answer(update, context):
	poll_answer = update.poll_answer
	poll_message = poll_msg(poll_answer.poll_id, context)
	chat_data = context.application.chat_data[poll_message.chat.id]
	answered_user = poll_answer.user.id
	intended_user = chat_data["current_player"].id
	if answered_user == intended_user:
		await poll_message.edit_reply_markup(make_take_markup(answered_user))
		chat_data["selected_dices"] = set(poll_answer.option_ids)


async def leave(update, context):
	user = update.effective_user

	if not context.chat_data.get("game_in_process", False):
		await update.message.reply_text("Игра не запущена")
	
	elif user == context.chat_data['initiator'] and context.chat_data["turn"] == 0:
		await update.message.reply_text("Организатор не может покинуть игру до её начала. Чтобы отменить игру, воспользуйся соответствующей кнопкой.")

	elif user not in context.chat_data["players"]:
		await update.message.reply_text("Ты не в списке участников")	

	else:
		await kick(user, context)
		await update.message.reply_text("Ты покинул(а) игру")


async def kick(user, context):
	del context.chat_data["players"][user]

	if context.chat_data["turn"] == 0:
		await context.chat_data["board"].edit_text(make_inviteboard(context), reply_markup=make_invite_markup(context), parse_mode="html")

	elif len(context.chat_data["players"]) <= 1:
		context.chat_data["game_in_process"] = 0
		try:
			await context.chat_data["board"].delete()
		except:
			pass # Continue if message was already deleted by user in personal chat
		context.application.create_task(delete_poll(context))
		if len(context.chat_data["players"]) == 1:
			context.chat_data["leaderboard"] += list(context.chat_data["players"])
			context.chat_data["board"] = await context.bot.send_message(
				chat_id=context._chat_id,
				text=make_leaderboard(context),
				parse_mode="html",
				disable_notification=True
			)

	elif context.chat_data["current_player"].id == user.id:
		context.application.create_task(delete_poll(context))
		await next_move(context)

	else:
		await context.chat_data["board"].edit_text(make_scoreboard(context), parse_mode="html")
		context.chat_data["player_iterator"] = iter(dict(context.chat_data["players"]))
		while next(context.chat_data["player_iterator"]) != context.chat_data["current_player"]:
			pass


async def ver(update, context):
	await update.message.reply_text("2025-02-20 03:03")

async def stat(update, context):
	active_games = []
	invites_waiting = []
	for chat_id, chat_data in context.application.chat_data.items():
		if chat_data.get("game_in_process", 0):
			if chat_data["turn"]:
				active_games.append(chat_id)
			else:
				invites_waiting.append(chat_id)
	await update.message.reply_text("Active games: " + str(active_games) + "\nInvites waiting: " + str(invites_waiting))


async def err_handler(update, context):
	try:
		raise context.error
	except (TelegramError, NetworkError, TimeoutError, ConnectionError) as e:
		er = e
		while er:
			tb = extract_tb(er.__traceback__)
			er = er.__cause__ or er.__context__
		stack_functions = [frame.name for frame in tb]
		logging.error(f"{type(e).__name__}: {e} (traceback: {', '.join(stack_functions)})")
	except Exception as e:
		logging.error(str(type(e).__name__), exc_info=True)


async def check_inactivity(context):
	current_time = time()
	for chat_id, chat_data in context.application.chat_data.items():
		if not chat_data.get("game_in_process", 0) or chat_data['turn'] == 0:
			continue
		if chat_data.get("move_begin_time", 9_999_999_999) + 900 < current_time:
			del chat_data["move_begin_time"]
			user = chat_data["current_player"]
			await kick(user, CallbackContext(context.application, chat_id=chat_id))
			await context.bot.send_message(
				chat_id=chat_id, 
				text=user.mention_html() + " кикнут(а), так как не закончил(а) ход за 15 минут.", 
				parse_mode='html'
			)


async def post_init(application):
	if not application.bot_data.get("poll_id:poll_msg", False):
		application.bot_data["poll_id:poll_msg"] = {}
	if not application.bot_data.get("chat_id:poll_msg", False):
		application.bot_data["chat_id:poll_msg"] = {}


async def create_poll(context):
	emo = "\uFE0F\u20E3"
	jokes = ["Рисковая игра!", "Йо-хо-хо!", "Кто не рискует - тот не пьёт!", "Риск - моё второе имя!", "Шансы 2 к 6!"]
	additional_opt = [choice(jokes)] if len(context.chat_data["current_roll"]) == 1 else []
	options = [str(i) + emo for i in context.chat_data["current_roll"]] + additional_opt
	keyboard = [[InlineKeyboardButton("Не забирать", callback_data=f"notake:{context.chat_data['current_player'].id}")]]
	poll_msg = await context.bot.send_poll(
		chat_id=context._chat_id,
		question=context.chat_data["current_player"].first_name + ", выбери кости",
		options=options,
		is_anonymous=False,
		allows_multiple_answers=True,
		reply_markup=InlineKeyboardMarkup(keyboard),
		disable_notification=True
	)
	context.bot_data["poll_id:poll_msg"][poll_msg.poll.id] = poll_msg
	context.bot_data["chat_id:poll_msg"][context._chat_id] = poll_msg


async def delete_poll(context):
	poll_msg = context.bot_data["chat_id:poll_msg"][context._chat_id]
	del context.bot_data["poll_id:poll_msg"][poll_msg.poll.id]
	del context.bot_data["chat_id:poll_msg"][context._chat_id]
	await sleep(0.5)
	try:
		await poll_msg.delete()
	except:
		pass # Continue if message was already deleted by user in personal chat


def poll_msg(poll_id, context):
	return context.bot_data["poll_id:poll_msg"][poll_id]


async def rules(update, context):
    string = (
    	"<b>Правила игры</b>\n"
        "Игроки по очереди бросают 6 кубиков и ищут комбинации в своём броске. "
        "Комбинации можно забрать в руку и получить очки, затем можно либо перебросить "
        "незабранные кубики и т.д., либо закончить ход. Если в броске нет ни одной "
        "комбинации, набранные за ход очки сгорают, и ход переходит к следующему. "
        "Если игроку удалось забрать все 6 костей, ему даётся ещё 6 и ход продолжается. "
        "Игра ведётся до 5000 очков, игроки занимают места в порядке достижения цели.\n"
        "\n<b>Комбинации</b>\n"
        "1\uFE0F\u20E3 - 100\n"
        "5\uFE0F\u20E3 - 50\n"
        "Три одинаковых \U000023FA\U000023FA\U000023FA - их номинал × 100\n"
        "Три единицы 1\uFE0F\u20E31\uFE0F\u20E31\uFE0F\u20E3 - 1000\n"
        "Каждая следующая такая же кость удваивает очки\n"
        "1\uFE0F\u20E32\uFE0F\u20E33\uFE0F\u20E3"
        "4\uFE0F\u20E35\uFE0F\u20E36\uFE0F\u20E3 - 1500\n"
        "<b>Только в классическом зонке:</b>\n"
        "Три пары \U000023FA\U000023FA\U0001F53C\U0001F53C\U000023F9\U000023F9 - 750\n"
        "<b>Только в бутовском зонке:</b>\n"
        "1\uFE0F\u20E32\uFE0F\u20E33\uFE0F\u20E34\uFE0F\u20E35\uFE0F\u20E3 - 500\n"
        "2\uFE0F\u20E33\uFE0F\u20E34\uFE0F\u20E35\uFE0F\u20E36\uFE0F\u20E3 - 750"
    )
    await update.message.reply_html(text=string, disable_notification=True)


async def send_help(update, context):
    string = (
        "Все команды:\n"
        "/start - Приветствие\n"
        "/help - Помощь\n"
        "/rules - Правила игры\n"
        "/zonk - Начать игру в зонк\n"
        "/zonk_b - Начать игру в бутовский зонк\n"
        "/leave - Покинуть игру\n"
        "Автор: https://t.me/Misha_Solovyev\n"
        "Исходный код: https://github.com/a17sol/play_zonk_bot"
    )
    await update.message.reply_text(
        text=string, 
        link_preview_options=LinkPreviewOptions(is_disabled=True), 
        disable_notification=True
    )


persistence = PicklePersistence(filepath='bot_memory.pikle')

application = Application.builder().token(token).persistence(persistence).post_init(post_init).build()

job_queue = application.job_queue
job_minute = job_queue.run_repeating(check_inactivity, interval=60)

application.add_handlers([
	CommandHandler("start", start),
	CommandHandler("zonk", zonk),
	CommandHandler("zonk_b", zonk_b),
	CommandHandler("leave", leave),
	CommandHandler("rules", rules),
	CommandHandler("help", send_help),
	CommandHandler("ver", ver),
	CommandHandler("stat", stat),
	CallbackQueryHandler(button_callback),
	PollAnswerHandler(poll_answer)
])

application.add_error_handler(err_handler)

application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)



