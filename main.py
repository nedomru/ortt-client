import asyncio
import websockets
import json
import re
import platform
import logging
import configparser
import os
import sys
import winreg
import ctypes
from dataclasses import dataclass
from typing import Optional, Any

# City mapping based on agreement ID prefix
CITY_MAPPING = {
    "22": "Барнаул", "32": "Брянск", "34": "Волга", "36": "Воронеж",
    "66": "Екатеринбург", "18": "Ижевск", "38": "Иркутск", "12": "Йошкар-Ола",
    "160": "Казань", "43": "Киров", "23": "Краснодар", "24": "Красноярск",
    "45": "Курган", "46": "Курск", "48": "Липецк", "27": "Магнитогорск",
    "481": "Мичуринск", "77": "Москва", "161": "Набережные Челны",
    "162": "Нижнекамск", "52": "Нижний Новгород", "54": "Новосибирск",
    "55": "Омск", "56": "Оренбург", "58": "Пенза", "59": "Пермь",
    "61": "Ростов-на-Дону", "62": "Рязань", "63": "Самара",
    "78": "Санкт-Петербург", "64": "Саратов", "30": "Селенгинск",
    "69": "Тверь", "70": "Томск", "71": "Тула", "72": "Тюмень",
    "303": "Улан-Удэ", "73": "Ульяновск", "10": "Уфа",
    "21": "Чебоксары", "17": "Челябинск", "76": "Ярославль"
}

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()


@dataclass
class ClientConfig:
    agreement_id: str
    city: str
    server_url: str
    autostart: bool


def add_to_windows_startup(program_path):
    """Add program to Windows startup"""
    try:
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        key_name = 'DiagnosticClient'

        # Request admin privileges
        if not ctypes.windll.shell32.IsUserAnAdmin():
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            return False

        # Open registry key
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
            winreg.SetValueEx(key, key_name, 0, winreg.REG_SZ, program_path)
        return True
    except Exception as e:
        logging.error(f"[Оперативник] Ошибка добавления в автозапуск: {e}")
        return False


def get_city_from_agreement_id(agreement_id: str) -> str:
    """Determine city based on agreement ID prefix"""
    for prefix, city in sorted(CITY_MAPPING.items(), key=lambda x: len(x[0]), reverse=True):
        if agreement_id.startswith(prefix):
            return city
    return "Undefined"


def load_or_create_config() -> ClientConfig:
    """Загрузка или создание конфигурации"""
    config = configparser.ConfigParser()
    config_path = 'config.ini'

    if not os.path.exists(config_path):
        # Default configuration with placeholder values
        default_config = {
            'DEFAULT': {
                'agreement_id': '',  # Placeholder agreement ID
                'city': '',  # Default city
                'server_url': 'ws://ort.chrsnv.ru:8765',
                'autostart': 'True'
            }
        }

        # Write default configuration
        with open(config_path, 'w') as configfile:
            config.read_dict(default_config)
            config.write(configfile)

    # Read the configuration
    config.read(config_path)

    # Convert string to bool for autostart
    autostart = config.getboolean('DEFAULT', 'autostart', fallback=True)

    # If autostart is enabled, add to Windows startup
    if autostart:
        executable_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
        add_to_windows_startup(executable_path)

    return ClientConfig(
        agreement_id=config['DEFAULT']['agreement_id'],
        city=get_city_from_agreement_id(config['DEFAULT']['agreement_id']),
        server_url=config['DEFAULT']['server_url'],
        autostart=autostart
    )


def parse_ping_output(output: str) -> Optional[dict]:
    """Extract ping statistics using regular expressions."""
    packet_loss_match = re.search(r"\((\d+)% �����\)", output)  # Packet loss
    min_rtt_match = re.search(r"�������쭮� = (\d+)�ᥪ", output)  # Min RTT
    avg_rtt_match = re.search(r"���ᨬ��쭮� = (\d+) �ᥪ", output)  # Avg RTT
    max_rtt_match = re.search(r"�।��� = (\d+) �ᥪ", output)  # Max RTT

    if all([packet_loss_match, min_rtt_match, avg_rtt_match, max_rtt_match]):
        return {
            "packet_loss": int(packet_loss_match.group(1)),
            "min_rtt": int(min_rtt_match.group(1)),
            "avg_rtt": int(avg_rtt_match.group(1)),
            "max_rtt": int(max_rtt_match.group(1))
        }
    else:
        logging.warning("[Оперативник] Ошибка обработки результата пинга. Голый вывод: %s", output)
        return None


def parse_tracert_output(output: str) -> list[dict[str, int | str | float | Any]] | None:
    """Parses the tracert output into a list of dictionaries with min/avg/max RTTs."""
    try:
        hops = []
        lines = output.strip().splitlines()

        # Skip header lines (adjust as needed for your tracert output format)
        data_lines = lines[3:]  # Start from the 4th line usually

        for line in data_lines:
            match = re.match(r"^\s*(\d+)\s+([\dms* ]+)\s+([\w.\-]+)?", line)  # Improved regex
            if match:
                hop_num = int(match.group(1))
                rtt_info = match.group(2).strip()
                ip_address = match.group(3) if match.group(3) else "*"

                rtts = [int(r) for r in rtt_info.split() if r.isdigit()]  # Extract numerical RTTs

                if rtts:
                    min_rtt = min(rtts)
                    avg_rtt = sum(rtts) / len(rtts)
                    max_rtt = max(rtts)
                else:
                    min_rtt = "*"
                    avg_rtt = "*"
                    max_rtt = "*"

                hops.append({
                    "hop": hop_num,
                    "ip": ip_address,
                    "min_rtt": min_rtt,
                    "avg_rtt": avg_rtt,
                    "max_rtt": max_rtt
                })
        return hops
    except Exception as e:
        logging.error(f"[Оперативник] Ошибка обработки результата трассировки: {e}")
        return None


async def run_diagnostic(command: str, target: str) -> str:
    """Выполнение диагностической команды"""
    try:
        logging.info(f"[Оперативник] Запущена команда {command} до ресурса {target}")
        process = await asyncio.create_subprocess_exec(
            command, target, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if stderr:
            try:
                err_decoded = stderr.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                err_decoded = stderr.decode(errors='replace')
            logging.error(f"[Оперативник] Ошибка команды: {err_decoded}")
            return f"Error: {err_decoded}"

        try:
            out_decoded = stdout.decode('utf-8', errors='replace')
        except UnicodeDecodeError:
            out_decoded = stdout.decode(errors='replace')

        logging.info(f"[Оперативник] Тест {command} до ресурса {target} завершен")
        if command == "ping":
            ping_stats = parse_ping_output(out_decoded)
            if ping_stats:
                return json.dumps(ping_stats)
            else:
                return "Error: Could not parse ping output"
        else:  # tracert
            tracert_data = parse_tracert_output(out_decoded)  # Parse tracert
            if tracert_data:
                return json.dumps(tracert_data)  # Return JSON
            else:
                return "Error: Could not parse tracert output"

    except Exception as e:
        logging.error(f"[Оперативник] Ошибка запуска диагностики: {e}")
        return f"Error: {str(e)}"


class DiagnosticClient:
    def __init__(self, config: ClientConfig):
        self.config = config
        self.websocket = None
        self.is_running = True

    async def connect(self):
        """Установка WebSocket соединения с сервером"""
        while self.is_running:
            try:
                async with websockets.connect(self.config.server_url) as websocket:
                    self.websocket = websocket
                    await self.register_client()
                    await self.message_handler()
            except websockets.ConnectionClosed:
                logging.warning("[Оперативник] Соединение потеряно, переподключаюсь...")
                await asyncio.sleep(5)
            except Exception as e:
                logging.error(f"[Оперативник] Ошибка подключения: {e}")
                await asyncio.sleep(5)

    async def register_client(self):
        """Регистрация клиента на сервере"""
        if self.config.agreement_id:
            registration_data = {
                "type": "registration",
                "data": {
                    "agreement_id": self.config.agreement_id,
                    "city": self.config.city,
                    "os": platform.system(),
                    "hostname": platform.node()
                }
            }

            logging.info("[Оперативник] Соединение установлено")
            await self.websocket.send(json.dumps(registration_data))
        else:
            logging.info("[Оперативник] Номер договора не указан в конфиге")
            sys.exit()

    async def message_handler(self):
        """Обработка входящих сообщений"""
        while self.is_running:
            try:
                message = await self.websocket.recv()
                await self.process_message(json.loads(message))
            except websockets.ConnectionClosed:
                break
            except json.JSONDecodeError:
                logging.error("[Оперативник] Получен некорректный JSON")
            except Exception as e:
                logging.error(f"[Оперативник] Ошибка обработки сообщения: {e}")

    async def process_message(self, message: dict):
        """Обработка команд от сервера"""
        if message.get("type") == "command":
            command = message.get("command")
            target = message.get("target")

            if command in ["tracert", "ping"]:
                result = await run_diagnostic(command, target)
                await self.send_result(command, target, result)

    async def send_result(self, command: str, target: str, result: str):
        """Отправка результатов на сервер"""
        response = {
            "type": "result",
            "agreement": self.config.agreement_id,
            "city": self.config.city,
            "command": command,
            "target": target,
            "result": result
        }
        await self.websocket.send(json.dumps(response))


async def main():
    try:
        config = load_or_create_config()
        client = DiagnosticClient(config)
        await client.connect()

    except Exception as e:
        logging.error(f"[Оперативник] Ошибка запуска клиента: {e}")


if __name__ == "__main__":
    asyncio.run(main())
