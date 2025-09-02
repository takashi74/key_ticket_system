import logging
import os

if not os.path.exists("logs"):
    os.makedirs("logs")

logger = logging.getLogger("key_ticket_system")
logger.setLevel(logging.DEBUG)

# コンソール
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

# ファイル（INFO）
fh_app = logging.FileHandler("logs/app.log")
fh_app.setLevel(logging.INFO)
fh_app.setFormatter(formatter)

# ファイル（ERROR専用）
fh_error = logging.FileHandler("logs/error.log")
fh_error.setLevel(logging.ERROR)
fh_error.setFormatter(formatter)

logger.addHandler(ch)
logger.addHandler(fh_app)
logger.addHandler(fh_error)
