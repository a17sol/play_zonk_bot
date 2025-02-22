import logging
import os
from traceback import extract_tb
# from telegram.error import TelegramError, NetworkError

from telegram.ext import Application, PicklePersistence

from handlers import register_handlers
from poll import register_poll_handler, poll_storage_init
from moderation import set_up_moderation


log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, "bot.log")

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s',
	handlers=[
		logging.FileHandler(log_path),
		logging.StreamHandler()
	]
)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)


token = os.getenv("ZONK_TOKEN")
if not token:
	logging.error("Token not set. Aborting.")
	exit()


async def err_handler(update, context):
	try:
		raise context.error
	# except (TelegramError, NetworkError, TimeoutError, ConnectionError) as e:
	# 	er = e
	# 	stack_functions = []
	# 	while er:
	# 		tb = extract_tb(er.__traceback__)
	# 		er = er.__cause__ or er.__context__
	# 		stack_functions.extend(["|"] + [frame.name for frame in tb])
	# 	logging.error(f"{type(e).__name__}: {e} (traceback: {', '.join(stack_functions)})")
	except Exception as e:
		logging.error(str(type(e).__name__), exc_info=True)


data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(data_dir, exist_ok=True)
persistence_file = os.path.join(data_dir, "bot_memory.pickle")

persistence = PicklePersistence(filepath=persistence_file)

application = Application.builder().token(token).persistence(persistence).post_init(poll_storage_init).build()

set_up_moderation(application)
register_handlers(application)
register_poll_handler(application)

application.add_error_handler(err_handler)

application.run_polling(allowed_updates=[], drop_pending_updates=True)
