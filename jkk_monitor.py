import time
import requests
import logging
from bs4 import BeautifulSoup
from threading import Lock

# ========= 定数エリア（依頼者のご要望によりenvなし） =========
JKK_URL = "https://jhomes.to-kousya.or.jp/search/jkknet/service/akiyaJyoukenStartInit"

# LINE Push API 用トークン（直接貼り付け）
LINE_CHANNEL_ACCESS_TOKEN = (
    "RJPmcANxL9ElYNk9pi/AVKxNA1oaLw3AcUNxfhXFM0/"
    "B54Ys29XMgrrMopve1I2bF7/fS3aln3Os2byl9mP7S7UW74dWsVWTm4zSztOrGux"
    "SViHtT6PpppoWtvtLpG+Raljjcu9cOxCc0ztz5iXLSwdB04t89/1O/w1cDnyilFU="
)
LINE_TO_ID = "C94caf4102b7be76772b6b5e3efd2d512"

CHECK_INTERVAL_SEC = 60
LOG_FILE = "jkk_monitor.log"
VACANCY_RECORD_FILE = "vacancy_status.txt"

# 監視対象の間取り
TARGET_TYPES = {
    "L2型": "2LDK／77.35㎡",
    "HL型": "3LDK／91.81㎡"
}

# ロギング設定
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ファイル書き込み排他用ロック
file_lock = Lock()

def send_line_message(message: str) -> bool:
    """LINE Push APIでメッセージを送信"""
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
    }
    payload = {
        "to": LINE_TO_ID,
        "messages": [{"type": "text", "text": message}]
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        logging.info(f"LINE送信成功: {resp.status_code}")
        return True
    except requests.RequestException as e:
        logging.error(f"LINE送信失敗: {e}")
        return False

def get_vacancy_info() -> dict:
    """JKKサイトから各間取りの空室状況を取得"""
    try:
        res = requests.get(JKK_URL, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"サイト取得エラー: {e}")
        raise

    soup = BeautifulSoup(res.text, "html.parser")
    status = {}
    for type_name in TARGET_TYPES:
        status[type_name] = False
    for tr in soup.select("table tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= 2:
            for type_name in TARGET_TYPES:
                if type_name in cells[0] and any(k in cells[1] for k in ("空", "募集中", "有")):
                    status[type_name] = True
    return status

def load_last_status() -> dict:
    """前回の空室状況をファイルから読み込む"""
    try:
        with file_lock, open(VACANCY_RECORD_FILE, "r", encoding="utf-8") as f:
            return {
                line.split(":", 1)[0]: line.split(":", 1)[1].strip() == "True"
                for line in f if ":" in line
            }
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"ステータス読み込みエラー: {e}")
        return {}

def save_status(status: dict):
    """最新の空室状況をファイルに書き込む"""
    try:
        with file_lock, open(VACANCY_RECORD_FILE, "w", encoding="utf-8") as f:
            for k, v in status.items():
                f.write(f"{k}:{v}\n")
    except Exception as e:
        logging.error(f"ステータス書き込みエラー: {e}")

def main():
    logging.info("==== JKK空室監視ツール 起動 ====")
    last_status = load_last_status()

    while True:
        try:
            current_status = get_vacancy_info()
            for type_name, is_open in current_status.items():
                previously_open = last_status.get(type_name, False)
                if is_open and not previously_open:
                    msg = f"【JKK空き通知】\n▶ {type_name} に空きが出ました！\n{JKK_URL}"
                    send_line_message(msg)
            save_status(current_status)
            last_status = current_status
        except Exception as e:
            logging.error(f"監視ループ内で例外発生: {e}")
        time.sleep(CHECK_INTERVAL_SEC)

if __name__ == "__main__":
    main()
