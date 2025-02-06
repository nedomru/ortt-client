import asyncio
import websockets
import json
import re
import platform
import logging
import configparser
import os
from dataclasses import dataclass
from typing import Optional

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='diagnostic_client.log'
)

@dataclass
class ClientConfig:
    agreement_id: str
    city: str
    server_url: str

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
                logging.warning("Connection lost. Reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logging.error(f"Connection error: {e}")
                await asyncio.sleep(5)

    async def register_client(self):
        """Регистрация клиента на сервере"""
        registration_data = {
            "type": "registration",
            "data": {
                "agreement_id": self.config.agreement_id,
                "city": self.config.city,
                "os": platform.system(),
                "hostname": platform.node()
            }
        }
        await self.websocket.send(json.dumps(registration_data))

    async def message_handler(self):
        """Обработка входящих сообщений"""
        while self.is_running:
            try:
                message = await self.websocket.recv()
                await self.process_message(json.loads(message))
            except websockets.ConnectionClosed:
                break
            except json.JSONDecodeError:
                logging.error("Received invalid JSON")
            except Exception as e:
                logging.error(f"Error processing message: {e}")

    async def process_message(self, message: dict):
        """Обработка команд от сервера"""
        if message.get("type") == "command":
            command = message.get("command")
            target = message.get("target")
            
            if command in ["tracert", "ping"]:
                result = await self.run_diagnostic(command, target)
                await self.send_result(command, target, result)

    async def run_diagnostic(self, command: str, target: str) -> str:
        """Выполнение диагностической команды"""
        try:
            if command == "ping":
                cmd = f"ping -n 30 -l 1200 {target}"
            else:
                cmd = f"tracert {target}"

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if stderr:
                try:
                    err_decoded = stderr.decode('utf-8', errors='replace')
                except:
                    err_decoded = stderr.decode(errors='replace')
                logging.error(f"Command error: {err_decoded}")
                return f"Error: {err_decoded}"

            try:
                out_decoded = stdout.decode('utf-8', errors='replace')
            except:
                out_decoded = stdout.decode(errors='replace')

            if command == "ping":
                ping_stats = self.parse_ping_output(out_decoded)
                if ping_stats:
                    return json.dumps(ping_stats)
                else:
                    return "Error: Could not parse ping output"
            else:  # tracert
                tracert_data = self.parse_tracert_output(out_decoded) # Parse tracert
                if tracert_data:
                    return json.dumps(tracert_data)  # Return JSON
                else:
                    return "Error: Could not parse tracert output"

        except Exception as e:
            logging.error(f"Error running diagnostic: {e}")
            return f"Error: {str(e)}"

    def parse_tracert_output(self, output: str) -> list:
        """Parses the tracert output into a list of dictionaries."""
        try:
            hops = []
            lines = output.strip().splitlines()

            # Skip header lines
            data_lines = lines[3:] # Start from the 4th line usually

            for line in data_lines:
                match = re.match(r"^\s*(\d+)\s+([\dms\* ]+)\s+([\w\.\-]+)?", line)  # Improved regex
                if match:
                    hop_num = int(match.group(1))
                    rtt_info = match.group(2).strip()
                    ip_address = match.group(3) if match.group(3) else "*"

                    rtts = [int(r) for r in rtt_info.split() if r.isdigit()] # Extract numerical RTTs
                    avg_rtt = sum(rtts) / len(rtts) if rtts else "*" # Calculate avg or "*"

                    hops.append({
                        "hop": hop_num,
                        "ip": ip_address,
                        "rtt": avg_rtt
                    })
            return hops
        except Exception as e:
            logging.error(f"Error parsing tracert output: {e}")
            return None
        
    def parse_ping_output(self, output: str) -> Optional[dict]:
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
          logging.warning("Could not parse ping statistics. Raw output: %s", output)
          return None

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

def load_config() -> ClientConfig:
    """Загрузка конфигурации из файла"""
    config = configparser.ConfigParser()
    config_path = 'config.ini'
    
    if not os.path.exists(config_path):
        # Создание конфигурации по умолчанию
        config['DEFAULT'] = {
            'agreement_id': '1234567890',
            'city': 'tyumen',
            'server_url': 'ws://ort.chrsnv.ru:8765'
        }
        with open(config_path, 'w') as f:
            config.write(f)
        raise Exception("Please fill in the config.ini file")
    
    config.read(config_path)
    return ClientConfig(
        agreement_id=config['DEFAULT']['agreement_id'],
        city=config['DEFAULT']['city'],
        server_url=config['DEFAULT']['server_url']
    )

async def main():
    try:
        config = load_config()
        client = DiagnosticClient(config)
        await client.connect()
    except Exception as e:
        logging.error(f"Failed to start client: {e}")

if __name__ == "__main__":
    asyncio.run(main())
