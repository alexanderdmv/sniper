import argparse
from pathlib import Path

from pipeline.launch_manager import LaunchManager
from utils.logger import setup_logger

logger = setup_logger("LAUNCH_BOT")

def main():
    parser = argparse.ArgumentParser(description="Solana Pump.fun Bundle Launch + Volume Bot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Сгенерировать 10-20 кошельков")
    g.add_argument("--num", type=int, default=15)

    l = sub.add_parser("launch", help="Создать токен + Jito bundle")
    l.add_argument("--name", required=True)
    l.add_argument("--symbol", required=True)
    l.add_argument("--desc", required=True)
    l.add_argument("--image", required=True, help="Путь к картинке (png/jpg)")
    l.add_argument("--buy", type=float, default=0.05, help="SOL на каждый кошелёк")

    v = sub.add_parser("volume", help="Запустить volume maker")
    v.add_argument("--cycles", type=int, default=20)
    v.add_argument("--interval", type=int, default=25)

    sub.add_parser("status", help="Показать кошельки")

    args = parser.parse_args()
    manager = LaunchManager()

    if args.cmd == "generate":
        manager.generate_wallets(args.num)
    elif args.cmd == "launch":
        manager.launch(args.name, args.symbol, args.desc, Path(args.image), args.buy)
    elif args.cmd == "volume":
        manager.start_volume_maker(args.cycles, args.interval)
    elif args.cmd == "status":
        manager.status()

if __name__ == "__main__":
    main()