
import os
import sys
import time
import shutil
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from config import config

BASE_DIR = Path(__file__).resolve().parent
SERVER_DIR = BASE_DIR / "server"
MODS_DIR = SERVER_DIR / "mods"
BACKUP_DIR = BASE_DIR / "backups"

JAVA = Path(config.JAVA_PATH)
MIN_RAM = config.MIN_RAM
MAX_RAM = config.MAX_RAM
Forge_Version = config.Forge_Version

process = None
reader_thread = None


def find_forge_jar():
    """Находит основной JAR-файл Forge."""
    candidates = [
        p for p in SERVER_DIR.glob(Forge_Version)
        if "installer" not in p.name.lower()
        and "sources" not in p.name.lower()
    ]

    # Сначала предпочитаем обычный серверный JAR.
    candidates.sort(key=lambda p: (
        "universal" in p.name.lower(),
        p.name
    ))

    if not candidates:
        return None

    if len(candidates) > 1:
        print("\nНайдены файлы Forge:")
        for i, candidate in enumerate(candidates, 1):
            print(f"[{i}] {candidate.name}")

        choice = input("Выбери файл (номер) или Enter для первого: ").strip()
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(candidates):
                return candidates[index]

    return candidates[0]


def read_output(proc):
    """Показывает вывод Java-процесса в реальном времени."""
    try:
        for line in proc.stdout:
            if line:
                print(f"[SERVER] {line}", end="", flush=True)
    except (ValueError, OSError):
        pass


def is_running():
    return process is not None and process.poll() is None


def start_server():
    global process, reader_thread

    if is_running():
        print("Сервер уже запущен.")
        return

    SERVER_DIR.mkdir(parents=True, exist_ok=True)
    MODS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    forge_jar = find_forge_jar()
    if forge_jar is None:
        print("Не найден JAR Forge в папке server.")
        print("Сначала установи Forge в:", SERVER_DIR)
        return

    print(f"Запуск: {forge_jar.name}")
    print(f"Выделенная память: {MIN_RAM}–{MAX_RAM}")

    command = [
        JAVA,
        f"-Xms{MIN_RAM}",
        f"-Xmx{MAX_RAM}",
        "-jar",
        forge_jar.name,
        "nogui",
    ]

    try:
        process = subprocess.Popen(
            command,
            cwd=str(SERVER_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        print("Java не найдена. Проверь установку Java 8 и PATH.")
        process = None
        return
    except OSError as error:
        print("Не удалось запустить сервер:", error)
        process = None
        return

    reader_thread = threading.Thread(
        target=read_output, args=(process,), daemon=True
    )
    reader_thread.start()
    print("Процесс сервера запущен. Ожидай сообщения Done.")


def send_command(command):
    if not is_running():
        print("Сервер не запущен.")
        return

    try:
        process.stdin.write(command + "\n")
        process.stdin.flush()
    except (OSError, ValueError) as error:
        print("Не удалось отправить команду:", error)


def stop_server():
    global process

    if not is_running():
        print("Сервер не запущен.")
        return

    print("Отправляю команду stop...")
    send_command("stop")

    try:
        process.wait(timeout=120)
        print("Сервер остановлен.")
    except subprocess.TimeoutExpired:
        print("Сервер не завершился за 120 секунд.")
        print("Не завершаю процесс принудительно, чтобы не повредить мир.")
        return


def backup_world():
    if is_running():
        print("Сначала останови сервер через меню.")
        return

    world_dir = SERVER_DIR / "world"
    if not world_dir.is_dir():
        print("Папка world не найдена.")
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_base = BACKUP_DIR / f"world_{timestamp}"

    try:
        archive = shutil.make_archive(
            str(archive_base), "zip",
            root_dir=str(SERVER_DIR),
            base_dir="world",
        )
        print("Резервная копия создана:", archive)
    except OSError as error:
        print("Ошибка резервного копирования:", error)


def show_status():
    if is_running():
        print(f"Сервер работает (PID: {process.pid}).")
    else:
        print("Сервер остановлен.")


def main():
    while True:
        print("\n" + "=" * 38)
        print("  MINECRAFT FORGE SERVER MANAGER")
        print("=" * 38)
        print("[1] Запустить сервер")
        print("[2] Остановить сервер")
        print("[3] Перезапустить сервер")
        print("[4] Показать статус")
        print("[5] Сделать резервную копию мира")
        print("[6] Отправить команду серверу")
        print("[0] Выход")

        choice = input("\nВыберите действие: ").strip()

        if choice == "1":
            start_server()
        elif choice == "2":
            stop_server()
        elif choice == "3":
            stop_server()
            if not is_running():
                time.sleep(2)
                start_server()
        elif choice == "4":
            show_status()
        elif choice == "5":
            backup_world()
        elif choice == "6":
            command = input("Команда Minecraft (без /): ").strip()
            if command:
                send_command(command)
        elif choice == "0":
            if is_running():
                print("Сначала останови сервер через пункт 2.")
            else:
                print("Выход.")
                break
        else:
            print("Неизвестный пункт меню.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nИспользуй пункт 2 для корректной остановки сервера.")