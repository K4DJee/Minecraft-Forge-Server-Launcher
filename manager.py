
import os
import sys
import time
import shutil
import threading
import subprocess

from pathlib import Path
from datetime import datetime
from queue import Queue, Empty

from config import config


# =========================
# CONFIGURATION
# =========================

BASE_DIR = Path(__file__).resolve().parent
SERVER_DIR = BASE_DIR / "server"
MODS_DIR = SERVER_DIR / "mods"
BACKUP_DIR = BASE_DIR / "backups"

JAVA = Path(config.JAVA_PATH)
MIN_RAM = config.MIN_RAM
MAX_RAM = config.MAX_RAM
Forge_Version = config.Forge_Version

BACKUP_INTERVAL = config.BACKUP_INTERVAL  # 45 минут
MAX_BACKUPS = config.MAX_BACKUPS           # Максимальное количество архивов

# =========================
# GLOBAL VARIABLES
# =========================

process = None
reader_thread = None

backup_thread = None
backup_stop_event = None

output_queue = Queue()
backup_lock = threading.Lock()


# =========================
# FORGE
# =========================

def find_forge_jar():
    """Находит основной JAR-файл Forge."""

    candidates = [
        p for p in SERVER_DIR.glob(Forge_Version)
        if "installer" not in p.name.lower()
        and "sources" not in p.name.lower()
    ]

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

        choice = input(
            "Выбери файл (номер) или Enter для первого: "
        ).strip()

        if choice.isdigit():
            index = int(choice) - 1

            if 0 <= index < len(candidates):
                return candidates[index]

    return candidates[0]


# =========================
# SERVER OUTPUT
# =========================

def read_output(proc):
    """Читает вывод Java-процесса."""

    try:
        for line in proc.stdout:
            if line:
                print(
                    f"[SERVER] {line}",
                    end="",
                    flush=True
                )

                output_queue.put(line)

    except (ValueError, OSError):
        pass


def clear_output_queue():
    """Очищает очередь старых сообщений."""

    while True:
        try:
            output_queue.get_nowait()
        except Empty:
            break


def wait_for_output(messages, timeout=60):
    """Ожидает одно из указанных сообщений сервера."""

    if isinstance(messages, str):
        messages = (messages,)

    messages = tuple(message.lower() for message in messages)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:

        remaining = deadline - time.monotonic()

        try:
            line = output_queue.get(timeout=remaining)
        except Empty:
            break

        line = line.lower()

        if any(message in line for message in messages):
            return True

    return False


# =========================
# SERVER STATUS
# =========================

def is_running():
    return process is not None and process.poll() is None


def show_status():
    if is_running():
        print(f"Сервер работает (PID: {process.pid}).")
    else:
        print("Сервер остановлен.")


# =========================
# SERVER COMMANDS
# =========================

def send_command(command):
    """Отправляет команду работающему серверу."""

    if not is_running():
        print("Сервер не запущен.")
        return False

    try:
        process.stdin.write(command + "\n")
        process.stdin.flush()
        return True

    except (OSError, ValueError) as error:
        print("Не удалось отправить команду:", error)
        return False


# =========================
# BACKUP MANAGEMENT
# =========================

def remove_old_backups():
    """Оставляет только последние MAX_BACKUPS архивов."""

    backups = sorted(
        BACKUP_DIR.glob("world_*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    for old_backup in backups[MAX_BACKUPS:]:
        try:
            old_backup.unlink()
            print("Удалён старый бэкап:", old_backup.name)

        except OSError as error:
            print(
                f"Не удалось удалить {old_backup.name}:",
                error
            )


def backup_world(automatic=False):
    """
    Создаёт резервную копию мира.

    Если сервер работает:
    1. Сохраняет мир.
    2. Отключает автоматическое сохранение.
    3. Создаёт архив.
    4. Включает автоматическое сохранение.
    """

    # Не допускаем одновременного создания нескольких архивов.
    with backup_lock:

        world_dir = SERVER_DIR / "world"

        if not world_dir.is_dir():
            print("Папка world не найдена.")
            return False

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        server_running = is_running()
        save_off_requested = False

        if server_running:

            print("\nПодготавливаю мир к резервному копированию...")

            # Сначала сохраняем изменения.
            clear_output_queue()

            if not send_command("save-all"):
                return False

            if not wait_for_output(
                ("saved the game", "saved the world"),
                timeout=180
            ):
                print("Не удалось подтвердить сохранение мира.")
                return False

            print("Мир сохранён.")

            # Отключаем автоматическое сохранение.
            clear_output_queue()

            if not send_command("save-off"):
                return False

            # Запоминаем, что команду отправили:
            # save-on должен выполниться даже при ошибке ожидания.
            save_off_requested = True

            if not wait_for_output(
                "automatic saving is now disabled",
                timeout=30
            ):
                print("Не удалось подтвердить отключение сохранения.")
                return False

            print("Автоматическое сохранение отключено.")

        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        archive_base = BACKUP_DIR / f"world_{timestamp}"

        try:

            print("Создаю резервную копию...")

            archive = shutil.make_archive(
                str(archive_base),
                "zip",
                root_dir=str(SERVER_DIR),
                base_dir="world"
            )

            print("Резервная копия создана:", archive)

            # Удаляем старые архивы.
            remove_old_backups()

            return True

        except OSError as error:

            print("Ошибка резервного копирования:", error)
            return False

        finally:

            # Обязательно возвращаем автоматическое сохранение.
            if save_off_requested and is_running():

                print("Включаю автоматическое сохранение...")

                if send_command("save-on"):
                    if wait_for_output(
                        "automatic saving is now enabled",
                        timeout=30
                    ):
                        print("Автоматическое сохранение включено.")
                    else:
                        print(
                            "Команда save-on отправлена, "
                            "но подтверждение не получено."
                        )


# =========================
# AUTOMATIC BACKUPS
# =========================

def automatic_backup_loop(stop_event):
    """Создаёт резервные копии каждые 45 минут."""

    print(
        "\n[AUTO BACKUP] "
        "Автоматические бэкапы включены (45 минут)."
    )

    while is_running():

        # Ожидание можно прервать при остановке сервера.
        if stop_event.wait(BACKUP_INTERVAL):
            break

        if not is_running():
            break

        print("\n[AUTO BACKUP] Начинаю резервное копирование...")

        backup_world(automatic=True)

    print("[AUTO BACKUP] Планировщик остановлен.")


# =========================
# SERVER START
# =========================

def start_server():
    global process
    global reader_thread
    global backup_stop_event
    global backup_thread

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
        str(JAVA),
        f"-Xms{MIN_RAM}",
        f"-Xmx{MAX_RAM}",
        "-jar",
        forge_jar.name,
        "nogui"
    ]

    try:

        clear_output_queue()

        process = subprocess.Popen(
            command,
            cwd=str(SERVER_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )

    except FileNotFoundError:

        print("Java не найдена. Проверь JAVA_PATH.")
        process = None
        return

    except OSError as error:

        print("Не удалось запустить сервер:", error)
        process = None
        return

    # Поток чтения вывода сервера.
    reader_thread = threading.Thread(
        target=read_output,
        args=(process,),
        daemon=True
    )

    reader_thread.start()

    # Поток автоматического резервного копирования.
    backup_stop_event = threading.Event()

    backup_thread = threading.Thread(
        target=automatic_backup_loop,
        args=(backup_stop_event,),
        daemon=True
    )

    backup_thread.start()

    print("Процесс сервера запущен. Ожидай сообщения Done.")


# =========================
# SERVER STOP
# =========================

def stop_server():
    global backup_stop_event
    global backup_thread

    if not is_running():
        print("Сервер не запущен.")
        return

    # Останавливаем планировщик.
    if backup_stop_event is not None:
        backup_stop_event.set()

    # Дожидаемся завершения текущего бэкапа.
    if backup_thread is not None and backup_thread.is_alive():

        print("Ожидаю завершения резервного копирования...")

        backup_thread.join()

    print("Отправляю команду stop...")

    if not send_command("stop"):
        return

    try:

        process.wait(timeout=120)
        print("Сервер остановлен.")

    except subprocess.TimeoutExpired:

        print("Сервер не завершился за 120 секунд.")
        print(
            "Не завершаю процесс принудительно, "
            "чтобы не повредить мир."
        )


# =========================
# MAIN MENU
# =========================

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

            command = input(
                "Команда Minecraft (без /): "
            ).strip()

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


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:

        print(
            "\nИспользуй пункт 2 для корректной остановки сервера."
        )
