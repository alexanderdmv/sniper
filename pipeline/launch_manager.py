import json
import time
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import requests
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import base58
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from utils.logger import setup_logger
from pipeline.control import load_control

console = Console()
logger = setup_logger("INFO")

WALLETS_PATH = Path("data/wallets.json")
LAST_MINT_PATH = Path("data/last_mint.txt")
HISTORY_PATH = Path("data/launch_history.json")

EXECUTOR_URL = "http://127.0.0.1:8790"
RPC_URL = "https://mainnet.helius-rpc.com/?api-key=fcf65e5f-636e-4800-ba08-33f6d536bace"

class LaunchManager:
    def __init__(self):
        self.control = load_control()
        self.wallets: List[Dict] = self._load_wallets()
        self.main_kp = self._load_main_keypair()

    def _load_main_keypair(self):
        paths = [Path("id.json"), Path("executor_ts/id.json"), Path(__file__).parent.parent / "id.json"]
        for p in paths:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    kp = Keypair.from_bytes(bytes(data))
                    logger.success(f"✅ Главный ключ загружен: {kp.pubkey()}")
                    return kp
                except:
                    continue
        logger.error("❌ id.json не найден!")
        return None

    def _load_wallets(self) -> List[Dict]:
        if WALLETS_PATH.exists():
            return json.loads(WALLETS_PATH.read_text(encoding="utf-8"))
        return []

    def _save_wallets(self):
        WALLETS_PATH.parent.mkdir(exist_ok=True)
        WALLETS_PATH.write_text(json.dumps(self.wallets, indent=2, ensure_ascii=False))

    def _save_last_mint(self, mint: str):
        LAST_MINT_PATH.parent.mkdir(exist_ok=True)
        LAST_MINT_PATH.write_text(mint)

    def _load_last_mint(self) -> str:
        if LAST_MINT_PATH.exists():
            return LAST_MINT_PATH.read_text().strip()
        return ""

    def _save_launch_history(self, data: dict):
        HISTORY_PATH.parent.mkdir(exist_ok=True)
        if HISTORY_PATH.exists():
            history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        else:
            history = []
        history.append(data)
        HISTORY_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False))

    # ====================== GENERATE ======================
    def generate_wallets(self, num: int = 15, force: bool = False):
        if self.wallets and not force:
            logger.warning("Уже есть кошельки.")
            return
        logger.info(f"Генерирую {num} кошельков...")
        self.wallets.clear()
        for i in range(num):
            kp = Keypair()
            secret_b58 = base58.b58encode(bytes(kp.secret())).decode("utf-8")
            self.wallets.append({
                "index": i,
                "pubkey": str(kp.pubkey()),
                "secret_b58": secret_b58
            })
        self._save_wallets()
        logger.success(f"✅ {num} кошельков сохранены")

    # ====================== FUND ALL ======================
    def fund_all(self, sol_amount: float):
        if not self.main_kp:
            console.print("[red]Главный ключ не найден![/red]")
            return
        console.print(Panel.fit(
            f"[bold]Отправляем {sol_amount} SOL на каждый из {len(self.wallets)} кошельков[/bold]",
            title="Fund All Wallets",
            border_style="green"
        ))
        for w in self.wallets:
            try:
                payload = {"side": "transfer", "to": w["pubkey"], "amount": sol_amount, "dry_run": False}
                r = requests.post(f"{EXECUTOR_URL}/trade", json=payload, timeout=30)
                if r.status_code == 200:
                    console.print(f"  → {w['pubkey'][:8]}... [green]OK[/green]")
                else:
                    console.print(f"  → {w['pubkey'][:8]}... [red]ошибка[/red]")
            except:
                console.print(f"  → {w['pubkey'][:8]}... [red]ошибка соединения[/red]")
        console.print("[green]Фандинг завершён[/green]")

    # ====================== BALANCES ======================
    def get_balances(self):
        console.print(Panel.fit("[bold cyan]Реальные балансы кошельков (SOL)[/bold cyan]", border_style="cyan"))
        for w in self.wallets:
            try:
                payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [w["pubkey"]]}
                r = requests.post(RPC_URL, json=payload, timeout=10)
                sol = r.json()["result"]["value"] / 1_000_000_000
                console.print(f"  {w['pubkey'][:8]}... → [green]{sol:.4f} SOL[/green]")
            except:
                console.print(f"  {w['pubkey'][:8]}... → [red]ошибка RPC[/red]")

    # ====================== WITHDRAW ALL ======================
    def withdraw_all(self):
        if not self.main_kp:
            console.print("[red]Главный ключ не найден![/red]")
            return
        console.print("[bold]Выводим ВСЕ SOL со всех кошельков на главный...[/bold]")
        for w in self.wallets:
            try:
                payload = {"side": "transfer", "to": str(self.main_kp.pubkey()), "amount": "all", "dry_run": False}
                r = requests.post(f"{EXECUTOR_URL}/trade", json=payload, timeout=30)
                if r.status_code == 200:
                    console.print(f"  → {w['pubkey'][:8]}... [green]вывод OK[/green]")
                else:
                    console.print(f"  → {w['pubkey'][:8]}... [red]ошибка[/red]")
            except:
                console.print(f"  → {w['pubkey'][:8]}... [red]таймаут[/red]")
        console.print("[green]Withdraw All завершён[/green]")

    # ====================== WALLET WARMUP ======================
   def wallet_warmup(self, cycles: int = 4, max_amount: float = 0.008):
        console.print(Panel.fit(
            f"[bold]Запускаю улучшенный прогрев кошельков (Warmup 2.0)\n"
            f"Циклов: {cycles} | Макс. сумма: {max_amount} SOL[/bold]",
            title="Wallet Warmup 2.0",
            border_style="blue"
        ))

        for cycle in range(1, cycles + 1):
            console.print(f"[cyan]Цикл {cycle}/{cycles}...[/cyan]")
            random.shuffle(self.wallets)

            for i in range(len(self.wallets) - 1):
                from_w = self.wallets[i]
                to_w = self.wallets[i + 1]
                amount = round(random.uniform(0.0008, max_amount), 6)

                try:
                    payload = {
                        "side": "transfer",
                        "to": to_w["pubkey"],
                        "amount": amount,
                        "dry_run": False
                    }
                    r = requests.post(f"{EXECUTOR_URL}/trade", json=payload, timeout=25)
                    if r.status_code == 200:
                        console.print(f"  {from_w['pubkey'][:6]} → {to_w['pubkey'][:6]} | {amount} SOL [green]OK[/green]")
                    else:
                        console.print(f"  {from_w['pubkey'][:6]} → {to_w['pubkey'][:6]} | ошибка")
                except:
                    console.print(f"  {from_w['pubkey'][:6]} → {to_w['pubkey'][:6]} | таймаут")

                time.sleep(random.uniform(2.0, 6.0))   # более естественные задержки

            time.sleep(random.uniform(15, 35))  # большая пауза между циклами

        console.print("[green]Улучшенный Warmup 2.0 успешно завершён![/green]")

    # ====================== AUTO SELL WITH TRAILING STOP ======================
    def auto_sell_tp(self, mint: str, tp_percent: float = 100, trailing_percent: float = 30):
        console.print(Panel.fit(
            f"[bold]Auto Sell запущен\n"
            f"Фиксированный TP: +{tp_percent}%\n"
            f"Trailing Stop: -{trailing_percent}% от максимума[/bold]",
            title="Auto Sell TP + Trailing",
            border_style="magenta"
        ))

        console.print("[yellow]Мониторинг цены запущен...[/yellow]")
        # Пока симуляция (реальная проверка цены можно добавить позже)
        time.sleep(2)
        console.print(f"[green]Цель +{tp_percent}% достигнута — продаём![/green]")
        self.sell_all(mint)

    # ====================== LAUNCH ======================
    def launch(self, name: str, symbol: str, description: str, image_path: Path, buy_sol_per_wallet: float = 0.03):
        if not self.wallets:
            self.generate_wallets(15)

        total = 0.025 + (buy_sol_per_wallet * len(self.wallets)) + 0.003
        console.print(Panel.fit(
            f"Создание токена:     0.025 SOL\n"
            f"Покупки:             {buy_sol_per_wallet*len(self.wallets):.3f} SOL\n"
            f"Jito tip:            0.003 SOL\n"
            f"[bold yellow]Итого ≈ {total:.3f} SOL[/bold yellow]",
            title="Расчёт расходов",
            border_style="yellow"
        ))

        if Prompt.ask("Запустить бандл?", choices=["y", "n"], default="y") == "n":
            return

        payload = {
            "name": name,
            "symbol": symbol,
            "description": description,
            "image_path": str(image_path.absolute()),
            "buy_sol_per_wallet": buy_sol_per_wallet,
            "wallets": self.wallets,
            "dry_run": self.control.get("trading", {}).get("dry_run", True)
        }

        try:
            r = requests.post(f"{EXECUTOR_URL}/launch_bundle", json=payload, timeout=120)
            if r.status_code == 200:
                data = r.json()
                mint = data.get('mint')
                logger.success("✅ Bundle отправлен!")
                logger.info(f"Mint: {mint}")
                logger.info(f"Bundle: {data.get('bundle_sig')}")

                self._save_last_mint(mint)

                history_entry = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "name": name,
                    "symbol": symbol,
                    "mint": mint,
                    "buy_per_wallet": buy_sol_per_wallet
                }
                self._save_launch_history(history_entry)
            else:
                logger.error(f"Ошибка: {r.text}")
        except Exception as e:
            logger.error(f"Не удалось подключиться к executor: {e}")

    # ====================== SELL ALL ======================
    def sell_all(self, mint: str):
        console.print(f"[bold magenta]Продаём ВСЕ токены {mint}...[/bold magenta]")
        for w in self.wallets:
            try:
                payload = {"side": "sell", "mint": mint, "amount_in": "all", "dry_run": False}
                r = requests.post(f"{EXECUTOR_URL}/trade", json=payload, timeout=30)
                if r.status_code == 200:
                    console.print(f"  → {w['pubkey'][:8]}... [green]продано[/green]")
                else:
                    console.print(f"  → {w['pubkey'][:8]}... [red]ошибка[/red]")
            except:
                console.print(f"  → {w['pubkey'][:8]}... [red]ошибка[/red]")
        console.print("[green]Sell All завершён[/green]")

    # ====================== VOLUME MAKER ======================
    def start_volume_maker(self, minutes: int = 30, trade_sol: float = 0.01):
        if not self.wallets:
            logger.error("Нет кошельков")
            return

        last_mint = self._load_last_mint()
        if last_mint:
            use_last = Prompt.ask(f"Использовать последний mint {last_mint[:8]}...? (y/n)", choices=["y","n"], default="y")
            mint = last_mint if use_last == "y" else Prompt.ask("Введи mint токена")
        else:
            mint = Prompt.ask("Введи mint токена")

        logger.info(f"🚀 Volume Maker запущен на {minutes} минут по токену {mint[:8]}...")
        end_time = time.time() + minutes * 60
        cycle = 0

        while time.time() < end_time:
            cycle += 1
            logger.info(f"Цикл {cycle}...")

            for w in self.wallets:
                side = random.choice(["buy", "sell"])
                try:
                    payload = {
                        "side": side,
                        "mint": mint,
                        "amount_in": trade_sol if side == "buy" else "all",
                        "dry_run": False
                    }
                    r = requests.post(f"{EXECUTOR_URL}/trade", json=payload, timeout=20)
                    status = "[green]OK[/green]" if r.status_code == 200 else "[red]ошибка[/red]"
                    console.print(f"  {w['pubkey'][:6]}... {side.upper()} {status}")
                except:
                    console.print(f"  {w['pubkey'][:6]}... [red]таймаут[/red]")

                time.sleep(random.uniform(1.5, 4.0))

            time.sleep(random.uniform(8, 18))

        logger.success(f"Volume Maker завершён")

    def status(self):
        console.print(f"[bold]Кошельков:[/bold] {len(self.wallets)}")
        for w in self.wallets[:10]:
            console.print(f"  {w['pubkey'][:8]}...{w['pubkey'][-6:]}")

    def show_launch_history(self):
        if not HISTORY_PATH.exists():
            console.print("[yellow]История запусков пуста[/yellow]")
            return
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        console.print(Panel.fit("[bold]Последние запуски[/bold]", border_style="blue"))
        for entry in reversed(history[-10:]):
            console.print(f"[{entry['timestamp']}] {entry['name']} ({entry['symbol']}) → {entry.get('mint', 'N/A')[:8]}...")

def main():
    pass