import json
import time
from pathlib import Path
from typing import List, Dict

import requests
from solders.keypair import Keypair
import base58

from utils.logger import setup_logger
from pipeline.control import load_control   # твой существующий

logger = setup_logger("LAUNCH")

WALLETS_PATH = Path("data/wallets.json")
EXECUTOR_URL = "http://127.0.0.1:8788"   # можно вынести в control.yaml позже

class LaunchManager:
    def __init__(self):
        self.control = load_control()
        self.wallets: List[Dict] = self._load_wallets()

    def _load_wallets(self) -> List[Dict]:
        if WALLETS_PATH.exists():
            return json.loads(WALLETS_PATH.read_text(encoding="utf-8"))
        return []

    def _save_wallets(self):
        WALLETS_PATH.parent.mkdir(exist_ok=True)
        WALLETS_PATH.write_text(json.dumps(self.wallets, indent=2, ensure_ascii=False))

    def generate_wallets(self, num: int = 15):
        if self.wallets:
            logger.warning(f"Уже есть {len(self.wallets)} кошельков. Генерирую только если нужно.")
            return
        logger.info(f"Генерирую {num} свежих кошельков...")
        for i in range(num):
            kp = Keypair()
            self.wallets.append({
                "index": i,
                "pubkey": str(kp.pubkey()),
                "secret_b58": base58.b58encode(kp.secret_key()).decode("utf-8")
            })
        self._save_wallets()
        logger.success(f"✅ {num} кошельков сохранены → {WALLETS_PATH}")

    def launch(self, name: str, symbol: str, description: str, image_path: Path,
               buy_sol_per_wallet: float = 0.05):
        if not self.wallets:
            self.generate_wallets(self.control.get("launch", {}).get("num_wallets", 15))

        payload = {
            "name": name,
            "symbol": symbol,
            "description": description,
            "image_path": str(image_path.absolute()),
            "buy_sol_per_wallet": buy_sol_per_wallet,
            "wallets": self.wallets,
            "dry_run": self.control.get("trading", {}).get("dry_run", True)
        }

        logger.info(f"Отправляю bundle create + {len(self.wallets)} buy...")
        r = requests.post(f"{EXECUTOR_URL}/launch_bundle", json=payload, timeout=90)
        
        if r.status_code == 200:
            data = r.json()
            logger.success("✅ Токен создан + Jito bundle отправлен!")
            logger.info(f"Mint: {data.get('mint')}")
            logger.info(f"Bundle: {data.get('bundle_sig')}")
            self.start_volume_maker()
        else:
            logger.error(f"❌ Ошибка executor: {r.text}")

    def start_volume_maker(self, cycles: int = 20, interval_sec: int = 25):
        logger.info("🚀 Запускаю volume maker (buy/sell между кошельками)...")
        # Здесь можно сделать полноценный цикл через executor /trade
        # Пока простой заглушка — потом доработаем
        for _ in range(cycles):
            for w in self.wallets:
                # вызов executor trade (buy → sell 0.01 SOL)
                time.sleep(0.4)
            time.sleep(interval_sec)
        logger.info("Volume maker завершён за сессию")

    def status(self):
        print(f"Кошельков всего: {len(self.wallets)}")
        for w in self.wallets[:10]:
            print(f"  {w['pubkey'][:8]}...{w['pubkey'][-6:]}")

# если хочешь fund/withdraw — скажи, добавлю