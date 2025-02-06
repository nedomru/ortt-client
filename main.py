import asyncio
import websockets
import json
import platform
import logging
import sys
from dataclasses import dataclass
import subprocess

from formatter import parse_ping_output, parse_tracert_output
from utility import ClientConfig, load_or_create_config

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def run_diagnostic(command: str, target: str) -> str:
    """Выполнение диагностической команды"""
    try:
        logging.info(f"[Оперативник] Запущена команда {command} до ресурса {target}")

        creationflags = subprocess.CREATE_NO_WINDOW
        process = await asyncio.create_subprocess_exec(
            command, target, 
            stdout=asyncio.subprocess.PIPE, 
            stderr=asyncio.subprocess.PIPE,
            creationflags=creationflags
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
        else:
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
