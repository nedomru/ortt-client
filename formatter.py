import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

def parse_ping_output(output: str) -> Optional[dict]:
    """Парсинг результат теста пинга используя регулярные выражения."""
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
    """Парсинг результат трассировки в список словарей, содержащий min/avg/max отклик."""
    try:
        hops = []
        lines = output.strip().splitlines()

        # Пропускаем заголовки
        data_lines = lines[3:]  # Ищем вывод с 4 строки

        for line in data_lines:
            match = re.match(r"^\s*(\d+)\s+([\dms* ]+)\s+([\w.\-]+)?", line)
            if match:
                hop_num = int(match.group(1))
                rtt_info = match.group(2).strip()
                ip_address = match.group(3) if match.group(3) else "*"

                rtts = [int(r) for r in rtt_info.split() if r.isdigit()]

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