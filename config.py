import os
import re
import glob
import shutil
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================
# Конфигурация
# ============================================
DB_CONFIG = {
    'host': "localhost",
    'database': "postgres",
    'user': "postgres",
    'password': os.getenv("db_pass"),
    'port': 5432
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ARCHIVE_DIR = os.path.join(BASE_DIR, 'archive')

FILE_PATTERNS = [
    'transactions_*.txt',
    'passport_blacklist_*.xlsx',
    'terminals_*.xlsx'
]

# ============================================
# Работа с БД
# ============================================
def get_connection():
    """Создает и возвращает подключение к базе данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return None

# ============================================
# Работа с файлами
# ============================================
def extract_date_from_filename(filename):
    """Извлекает дату из имени файла по шаблону DDMMYYYY"""
    match = re.search(r'_(\d{2})(\d{2})(\d{4})', filename)
    if match:
        day, month, year = match.groups()
        return datetime(int(year), int(month), int(day)).date()
    return None

def find_files_to_process():
    """Находит все файлы в DATA_DIR для обработки"""
    all_files = []
    for pattern in FILE_PATTERNS:
        search_path = os.path.join(DATA_DIR, pattern)
        print(f"Поиск файлов по шаблону: {search_path}")
        found_files = glob.glob(search_path)
        print(f"Найдено: {len(found_files)}")
        all_files.extend(found_files)
    return all_files

def archive_file(file_path):
    """Перемещает обработанный файл в архив с расширением .backup"""
    try:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        base_name = os.path.basename(file_path)
        archive_name = base_name + '.backup'
        archive_path = os.path.join(ARCHIVE_DIR, archive_name)
        
        if os.path.exists(archive_path):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = f"{base_name}.{timestamp}.backup"
            archive_path = os.path.join(ARCHIVE_DIR, archive_name)
        
        shutil.move(file_path, archive_path)
        print(f"  Файл перемещен в архив: {archive_path}")
        return True
    except Exception as e:
        print(f"  Ошибка при архивации файла {file_path}: {e}")
        return False

# ============================================
# Метаданные
# ============================================
class MetadataManager:
    """Класс для управления метаданными загрузок"""
    
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()
    
    def is_file_processed(self, file_name):
        try:
            self.cur.execute("""
                SELECT 1 FROM dwh.META_LOAD_HISTORY
                WHERE file_name = %s AND status = 'SUCCESS'
            """, (file_name,))
            return self.cur.fetchone() is not None
        except Exception as e:
            print(f"  Ошибка при проверке файла: {e}")
            return False
    
    def mark_file_processed(self, file_name, file_date, rows_loaded, status='SUCCESS', error=None):
        try:
            self.cur.execute("""
                INSERT INTO dwh.META_LOAD_HISTORY 
                (file_name, file_date, status, rows_loaded, error_message, load_dt)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (file_name, file_date, status, rows_loaded, error))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"  Ошибка при отметке файла: {e}")
            self.conn.rollback()
            return False
    
    def reset_file_status(self, file_name):
        try:
            self.cur.execute("""
                DELETE FROM dwh.META_LOAD_HISTORY
                WHERE file_name = %s
            """, (file_name,))
            self.conn.commit()
            print(f"  Сброшен статус файла: {file_name}")
            return True
        except Exception as e:
            print(f"  Ошибка при сбросе статуса: {e}")
            return False