import configparser
import ctypes
import logging
import os
import sys
import winreg
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Префиксы договоров по городам
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


@dataclass
class ClientConfig:
    agreement_id: str
    city: str
    server_url: str
    autostart: bool


def add_to_windows_startup(program_path):
    """Добавление программы в автозапуск"""
    try:
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        key_name = 'ort'

        # Запрашиваем права администратора
        if not ctypes.windll.shell32.IsUserAnAdmin():
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            return False

        # Открываем ключ в реестре
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
        # Стандартный конфиг
        default_config = {
            'DEFAULT': {
                'agreement_id': '',
                'server_url': 'ws://ort.chrsnv.ru:8765',
                'autostart': 'True'
            }
        }

        # Запись конфига
        with open(config_path, 'w') as configfile:
            config.read_dict(default_config)
            config.write(configfile)

    # Чтение конфига
    config.read(config_path)

    # Convert string to bool for autostart
    autostart = config.getboolean('DEFAULT', 'autostart', fallback=True)

    # Если включен автозапуск - активируем его
    if autostart:
        executable_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
        add_to_windows_startup(executable_path)

    return ClientConfig(
        agreement_id=config['DEFAULT']['agreement_id'],
        city=get_city_from_agreement_id(config['DEFAULT']['agreement_id']),
        server_url=config['DEFAULT']['server_url'],
        autostart=autostart
    )
