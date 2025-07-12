#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JKK賃貸監視ツール - トミンハイム古石場二丁目 空室監視システム
監視対象: L2型（2LDK／77.35㎡）、HL型（3LDK／91.81㎡）
"""

import time
import requests
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
import os
import json

# 設定
JKK_LOGIN_ID = "c415f0d6"
JKK_LOGIN_PASS = "9648Kotarou2025"
LINE_ACCESS_TOKEN = "RJPmcANxL9ElYNk9pi/AVKxNA1oaLw3AcUNxfhXFM0/B54Ys29XMgrrMopve1I2bF7/fS3aln3Os2byl9mP7S7UW74dWsVWTm4zSztOrGuxSViHtT6PpppoWtvtLpG+Raljjcu9cOxCc0ztz5iXLSwdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "c1c83637d6f4a2cfb3db2c32550d8656"

# URL設定
BASE_URL = "https://www.to-kousya.or.jp/chintai/reco/th_furuishiba2.html"
TARGET_ROOM_TYPES = ["L2", "HL"]

# ログ設定
LOG_FILE = "/var/log/jkk_monitor.log"
STATE_FILE = "/var/lib/jkk_monitor_state.json"

# ログ設定の初期化
def setup_logging():
    """ログ設定を初期化"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

class JKKMonitor:
    def __init__(self):
        self.driver = None
        self.previous_state = self.load_state()
        
    def setup_driver(self):
        """Seleniumドライバーの設定"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # ヘッドレスモード
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Chromeドライバーの初期化完了")
        except Exception as e:
            logger.error(f"Chromeドライバーの初期化に失敗: {e}")
            raise
    
    def load_state(self):
        """前回の状態を読み込み"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"状態ファイルの読み込みに失敗: {e}")
        return {}
    
    def save_state(self, state):
        """現在の状態を保存"""
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"状態ファイルの保存に失敗: {e}")
    
    def send_line_notification(self, message):
        """LINE通知を送信"""
        url = "https://notify-api.line.me/api/notify"
        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"message": message}
        
        try:
            response = requests.post(url, headers=headers, data=data)
            if response.status_code == 200:
                logger.info("LINE通知送信成功")
                return True
            else:
                logger.error(f"LINE通知送信失敗: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"LINE通知送信エラー: {e}")
            return False
    
    def check_vacancy(self):
        """空室情報をチェック"""
        try:
            logger.info("空室情報チェック開始")
            
            # メインページにアクセス
            self.driver.get(BASE_URL)
            time.sleep(3)
            
            # 「最新の空き室状況を確認する」ボタンを探してクリック
            try:
                # 様々なセレクターを試す
                button_selectors = [
                    "//a[contains(text(), '最新の空き室状況を確認する')]",
                    "//button[contains(text(), '最新の空き室状況を確認する')]",
                    "//input[contains(@value, '最新の空き室状況を確認する')]",
                    "//a[contains(@href, 'vacancy')]",
                    "//a[contains(@href, 'akishitsu')]",
                    "//a[contains(@class, 'vacancy')]",
                    "//a[contains(@class, 'check')]"
                ]
                
                button_found = False
                for selector in button_selectors:
                    try:
                        button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        button.click()
                        button_found = True
                        logger.info(f"ボタンクリック成功: {selector}")
                        break
                    except TimeoutException:
                        continue
                
                if not button_found:
                    logger.warning("空室状況確認ボタンが見つかりません")
                    # ページのHTMLを確認
                    page_source = self.driver.page_source
                    if "空き室" in page_source or "空室" in page_source:
                        logger.info("ページに空室情報が含まれています")
                    else:
                        logger.warning("ページに空室情報が見つかりません")
                
                time.sleep(5)  # ページロード待機
                
            except Exception as e:
                logger.warning(f"ボタンクリック処理でエラー: {e}")
            
            # 現在のページで空室情報を取得
            current_state = {}
            
            # L2型とHL型の空室情報を検索
            for room_type in TARGET_ROOM_TYPES:
                vacancy_found = self.check_room_type_vacancy(room_type)
                current_state[room_type] = vacancy_found
                
                if vacancy_found:
                    logger.info(f"{room_type}型の空室を発見！")
                    
                    # 前回の状態と比較して新しい空室の場合のみ通知
                    if self.previous_state.get(room_type, False) != vacancy_found:
                        message = f"""【JKK空き通知】
トミンハイム古石場二丁目
▶ {room_type}型 に空きが出ました！
{BASE_URL}
検知時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                        self.send_line_notification(message)
                else:
                    logger.info(f"{room_type}型に空室なし")
            
            # 状態を保存
            self.save_state(current_state)
            self.previous_state = current_state
            
            return current_state
            
        except Exception as e:
            logger.error(f"空室チェック処理でエラー: {e}")
            return None
    
    def check_room_type_vacancy(self, room_type):
        """指定された部屋タイプの空室をチェック"""
        try:
            page_source = self.driver.page_source.lower()
            
            # 部屋タイプに関連するキーワードを検索
            room_keywords = {
                "L2": ["l2", "2ldk", "77.35", "77㎡"],
                "HL": ["hl", "3ldk", "91.81", "91㎡"]
            }
            
            # 空室を示すキーワード
            vacancy_keywords = ["空き", "空室", "募集", "○", "available", "vacancy"]
            
            # 満室を示すキーワード
            full_keywords = ["満室", "×", "full", "申込中", "契約済"]
            
            # 部屋タイプが存在するかチェック
            room_found = False
            for keyword in room_keywords.get(room_type, []):
                if keyword in page_source:
                    room_found = True
                    break
            
            if not room_found:
                logger.warning(f"{room_type}型の情報がページに見つかりません")
                return False
            
            # 部屋タイプ周辺のテキストを解析
            # より詳細な解析を行う場合は、BeautifulSoupを使用
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # テーブルや一覧形式での情報を検索
            tables = soup.find_all(['table', 'div', 'ul', 'li'])
            
            for element in tables:
                element_text = element.get_text().lower()
                
                # 部屋タイプが含まれる要素を探す
                type_match = False
                for keyword in room_keywords.get(room_type, []):
                    if keyword in element_text:
                        type_match = True
                        break
                
                if type_match:
                    # 同じ要素内に空室情報があるかチェック
                    for vacancy_keyword in vacancy_keywords:
                        if vacancy_keyword in element_text:
                            # 満室キーワードがないことを確認
                            has_full_keyword = any(full_keyword in element_text for full_keyword in full_keywords)
                            if not has_full_keyword:
                                return True
            
            return False
            
        except Exception as e:
            logger.error(f"部屋タイプ{room_type}の空室チェックでエラー: {e}")
            return False
    
    def run_monitor(self):
        """監視処理を実行"""
        try:
            self.setup_driver()
            result = self.check_vacancy()
            
            if result:
                logger.info(f"監視完了: {result}")
            else:
                logger.warning("監視処理が正常に完了しませんでした")
                
        except Exception as e:
            logger.error(f"監視処理でエラー: {e}")
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("ドライバーを終了しました")
    
    def test_line_notification(self):
        """LINE通知のテスト"""
        test_message = f"""【JKK監視ツール】
テスト通知です
起動時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
監視対象: トミンハイム古石場二丁目 (L2型・HL型)"""
        
        return self.send_line_notification(test_message)

def main():
    """メイン処理"""
    logger.info("JKK監視ツールを開始します")
    
    monitor = JKKMonitor()
    
    # 起動時にテスト通知を送信
    if monitor.test_line_notification():
        logger.info("テスト通知送信完了")
    else:
        logger.error("テスト通知送信失敗")
    
    # 監視処理を実行
    monitor.run_monitor()
    
    logger.info("JKK監視ツールを終了します")

if __name__ == "__main__":
    main()
