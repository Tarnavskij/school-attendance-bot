# sigur_reader.py
import asyncio
from datetime import datetime
import pymysql
from logger import get_logger
from repositories import get_teacher_by_card_number, update_teacher_status
from config import DEFAULT_SCHOOL_ID

logger = get_logger(__name__)

# --- Конфигурация подключения к MariaDB Sigur ---
# ЗАМЕНИТЕ ЭТИ ЗНАЧЕНИЯ НА СВОИ!
SIGUR_DB_HOST = 'localhost'          # или IP-адрес сервера Sigur
SIGUR_DB_PORT = 3305                 # порт из вашего sphinx.ini
SIGUR_DB_USER = 'ваш_логин'          # логин (скорее всего root)
SIGUR_DB_PASSWORD = 'ваш_пароль'     # пароль
SIGUR_DB_NAME = 'tc-db-log'          # база с логами

def get_sigur_connection():
    """Возвращает соединение с MariaDB."""
    return pymysql.connect(
        host=SIGUR_DB_HOST,
        port=SIGUR_DB_PORT,
        user=SIGUR_DB_USER,
        password=SIGUR_DB_PASSWORD,
        database=SIGUR_DB_NAME,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def fetch_new_events(last_time: datetime | None):
    """
    Возвращает список новых событий (словарей) из v_logs.
    Если last_time None — берёт события за последние 5 минут.
    """
    with get_sigur_connection() as conn:
        with conn.cursor() as cur:
            if last_time is None:
                sql = """
                    SELECT ID, LOGTIME, EMPHINT, DIRECTION
                    FROM v_logs
                    WHERE ACCESS_OBJECT_TYPE_ID = 'EMP'
                      AND LOGTIME > NOW() - INTERVAL 5 MINUTE
                    ORDER BY LOGTIME
                """
                cur.execute(sql)
            else:
                sql = """
                    SELECT ID, LOGTIME, EMPHINT, DIRECTION
                    FROM v_logs
                    WHERE ACCESS_OBJECT_TYPE_ID = 'EMP'
                      AND LOGTIME > %s
                    ORDER BY LOGTIME
                """
                cur.execute(sql, (last_time,))
            return cur.fetchall()

def get_employee_info(emphint: int):
    """
    Возвращает (name, card_number) для сотрудника по EMPHINT.
    """
    with get_sigur_connection() as conn:
        with conn.cursor() as cur:
            # Имя сотрудника
            cur.execute("SELECT NAME FROM tc-db-main.personal WHERE ID = %s", (emphint,))
            row = cur.fetchone()
            if not row:
                return None, None
            name = row['NAME']
            # Номер карты
            cur.execute(
                """SELECT formatted_value FROM tc-db-main.assigned_identifiers
                   WHERE access_object_id = %s AND type = 'CARD' LIMIT 1""",
                (emphint,)
            )
            row2 = cur.fetchone()
            card_number = row2['formatted_value'] if row2 else None
            return name, card_number

class SigurWatcher:
    def __init__(self, callback):
        self.callback = callback
        self.last_time = None
        self.running = False

    async def run(self, interval: float = 1.0):
        self.running = True
        logger.info("Запущен watcher для Sigur")
        while self.running:
            try:
                events = fetch_new_events(self.last_time)
                if events:
                    self.last_time = events[-1]['LOGTIME']
                    for ev in events:
                        name, card = get_employee_info(ev['EMPHINT'])
                        if name and card:
                            ev['employee_name'] = name
                            ev['card_number'] = card
                            await self.callback(ev)
                        else:
                            logger.debug(f"Неизвестный EMPHINT={ev['EMPHINT']}")
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Ошибка в Sigur watcher: {e}", exc_info=True)
                await asyncio.sleep(interval)

    def stop(self):
        self.running = False