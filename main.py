import pandas as pd
import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta
import os
import shutil
import glob
import re
from dotenv import load_dotenv

load_dotenv()

# ============================================
# 1. Параметры подключения к базе данных
# ============================================
DB_CONFIG = {
    'host': "localhost",
    'database': "postgres",
    'user': "postgres",
    'password': os.getenv("db_pass"),
    'port': 5432
}

# Директории
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ARCHIVE_DIR = os.path.join(BASE_DIR, 'archive')

print(f"BASE_DIR: {BASE_DIR}")
print(f"DATA_DIR: {DATA_DIR}")
print(f"ARCHIVE_DIR: {ARCHIVE_DIR}")

# Создаем директории если их нет
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# ============================================
# 2. Класс для работы с метаданными
# ============================================
class MetadataManager:
    """Класс для управления метаданными загрузок"""
    
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()
    
    def is_file_processed(self, file_name):
        """Проверяет, был ли файл уже обработан"""
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
        """Отмечает файл как обработанный"""
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
        """Сбрасывает статус файла для повторной обработки"""
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

# ============================================
# 3. Вспомогательные функции
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

def extract_date_from_filename(filename):
    """Извлекает дату из имени файла по шаблону DDMMYYYY"""
    # Паттерн для DDMMYYYY
    match = re.search(r'_(\d{2})(\d{2})(\d{4})', filename)
    if match:
        day, month, year = match.groups()
        return datetime(int(year), int(month), int(day)).date()
    return None

def find_files_to_process():
    """Находит все файлы в DATA_DIR для обработки"""
    all_files = []
    
    patterns = [
        'transactions_*.txt',
        'passport_blacklist_*.xlsx',
        'terminals_*.xlsx'
    ]
    
    for pattern in patterns:
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
        
        # Если файл уже существует в архиве, добавляем timestamp
        if os.path.exists(archive_path):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = f"{base_name}.{timestamp}.backup"
            archive_path = os.path.join(ARCHIVE_DIR, archive_name)
        
        # Перемещаем файл в архив
        shutil.move(file_path, archive_path)
        print(f"  Файл перемещен в архив: {archive_path}")
        
        return True
    except Exception as e:
        print(f"  Ошибка при архивации файла {file_path}: {e}")
        return False

# ============================================
# 4. Функции загрузки данных в STG
# ============================================
def load_transactions_to_stg(file_path, conn, load_date):
    """Загружает CSV-файл с транзакциями в STG_TRANSACTIONS"""
    try:
        print(f"\nЗагрузка транзакций: {os.path.basename(file_path)}")
        
        # Читаем CSV с правильными параметрами
        df = pd.read_csv(
            file_path,
            sep=';',
            encoding='utf-8',
            decimal=',',
            parse_dates=['transaction_date']
        )
        
        print(f"  Прочитано строк: {len(df)}")
        
        # Фильтруем только транзакции за дату файла
        df['transaction_date_only'] = df['transaction_date'].dt.date
        df_filtered = df[df['transaction_date_only'] == load_date]
        print(f"  Строк за {load_date}: {len(df_filtered)}")
        
        if len(df_filtered) == 0:
            print(f"  Нет данных за {load_date}, пропускаем")
            return 0
        
        cur = conn.cursor()
        
        # Очищаем STG перед загрузкой
        cur.execute("TRUNCATE TABLE dwh.STG_TRANSACTIONS;")
        
        # Вставляем данные
        inserted = 0
        for _, row in df_filtered.iterrows():
            cur.execute("""
                INSERT INTO dwh.STG_TRANSACTIONS (
                    transaction_id, transaction_date, amount, card_num, 
                    oper_type, oper_result, terminal
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                str(row['transaction_id']),
                row['transaction_date'],
                float(row['amount']),
                row['card_num'],
                row['oper_type'],
                row['oper_result'],
                row['terminal']
            ))
            inserted += 1
        
        conn.commit()
        cur.close()
        
        print(f"  Загружено {inserted} строк в STG_TRANSACTIONS")
        return inserted
        
    except Exception as e:
        print(f"  Ошибка при загрузке транзакций: {e}")
        conn.rollback()
        raise

def load_terminals_to_stg(file_path, conn):
    """Загружает XLSX-файл с терминалами в STG_TERMINALS"""
    try:
        print(f"\nЗагрузка терминалов: {os.path.basename(file_path)}")
        
        df = pd.read_excel(file_path)
        print(f"  Прочитано строк: {len(df)}")
        
        cur = conn.cursor()
        
        # Очищаем STG перед загрузкой
        cur.execute("TRUNCATE TABLE dwh.STG_TERMINALS;")
        
        inserted = 0
        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO dwh.STG_TERMINALS (
                    terminal_id, terminal_type, terminal_city, terminal_address
                ) VALUES (%s, %s, %s, %s)
            """, (
                row['terminal_id'],
                row['terminal_type'],
                row['terminal_city'],
                row['terminal_address']
            ))
            inserted += 1
        
        conn.commit()
        cur.close()
        
        print(f"  Загружено {inserted} строк в STG_TERMINALS")
        return inserted
        
    except Exception as e:
        print(f"  Ошибка при загрузке терминалов: {e}")
        conn.rollback()
        raise

def load_blacklist_to_stg(file_path, conn):
    """Загружает XLSX-файл с черным списком в STG_PASSPORT_BLACKLIST"""
    try:
        print(f"\nЗагрузка черного списка: {os.path.basename(file_path)}")
        
        df = pd.read_excel(file_path)
        print(f"  Прочитано строк: {len(df)}")
        
        cur = conn.cursor()
        
        # Очищаем STG перед загрузкой
        cur.execute("TRUNCATE TABLE dwh.STG_PASSPORT_BLACKLIST;")
        
        inserted = 0
        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO dwh.STG_PASSPORT_BLACKLIST (entry_dt, passport_num)
                VALUES (%s, %s)
            """, (
                row['date'],
                row['passport']
            ))
            inserted += 1
        
        conn.commit()
        cur.close()
        
        print(f"  Загружено {inserted} строк в STG_PASSPORT_BLACKLIST")
        return inserted
        
    except Exception as e:
        print(f"  Ошибка при загрузке черного списка: {e}")
        conn.rollback()
        raise

# ============================================
# 5. Функции загрузки из STG в DWH
# ============================================
def load_terminals_to_dim_hist(conn, load_date):
    """Загружает терминалы в DWH_DIM_TERMINALS_HIST по SCD2"""
    try:
        print(f"\nЗагрузка терминалов в DWH_DIM_TERMINALS_HIST на {load_date}")
        
        cur = conn.cursor()
        
        # Закрываем старые версии терминалов, которых нет в новом срезе
        cur.execute("""
            UPDATE dwh.DWH_DIM_TERMINALS_HIST t
            SET effective_to = %s::TIMESTAMP
            WHERE effective_to IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM dwh.STG_TERMINALS s
                WHERE s.terminal_id = t.terminal_id
            );
        """, (load_date,))
        
        closed_count = cur.rowcount
        if closed_count > 0:
            print(f"  Закрыто удаленных терминалов: {closed_count}")
        
        # Добавляем новые версии терминалов (новые или изменившиеся)
        cur.execute("""
            INSERT INTO dwh.DWH_DIM_TERMINALS_HIST (
                terminal_id, terminal_type, terminal_city, terminal_address,
                effective_from, effective_to, deleted_flg
            )
            SELECT 
                s.terminal_id,
                s.terminal_type,
                s.terminal_city,
                s.terminal_address,
                %s::TIMESTAMP,
                NULL,
                FALSE
            FROM dwh.STG_TERMINALS s
            WHERE NOT EXISTS (
                SELECT 1 FROM dwh.DWH_DIM_TERMINALS_HIST t
                WHERE t.terminal_id = s.terminal_id
                AND t.effective_to IS NULL
                AND t.terminal_type = s.terminal_type
                AND t.terminal_city = s.terminal_city
                AND t.terminal_address = s.terminal_address
            );
        """, (load_date,))
        
        inserted_count = cur.rowcount
        print(f"  Добавлено новых/измененных: {inserted_count}")
        
        conn.commit()
        cur.close()
        return True
        
    except Exception as e:
        print(f"  Ошибка при загрузке терминалов: {e}")
        conn.rollback()
        return False

def load_blacklist_to_fact(conn):
    """Загружает записи из STG в DWH_FACT_PASSPORT_BLACKLIST (инкрементально)"""
    try:
        print("\nЗагрузка черного списка в DWH_FACT_PASSPORT_BLACKLIST")
        
        cur = conn.cursor()
        
        # Вставляем только новые записи
        cur.execute("""
            INSERT INTO dwh.DWH_FACT_PASSPORT_BLACKLIST (entry_dt, passport_num)
            SELECT s.entry_dt, s.passport_num
            FROM dwh.STG_PASSPORT_BLACKLIST s
            WHERE NOT EXISTS (
                SELECT 1 FROM dwh.DWH_FACT_PASSPORT_BLACKLIST f
                WHERE f.passport_num = s.passport_num
                AND f.entry_dt = s.entry_dt
            );
        """)
        
        inserted_count = cur.rowcount
        conn.commit()
        cur.close()
        
        print(f"  Добавлено новых записей: {inserted_count}")
        return True
        
    except Exception as e:
        print(f"  Ошибка при загрузке черного списка: {e}")
        conn.rollback()
        return False

def load_transactions_to_fact(conn):
    """Загружает транзакции из STG в DWH_FACT_TRANSACTIONS"""
    try:
        print("\nЗагрузка транзакций в DWH_FACT_TRANSACTIONS")
        
        cur = conn.cursor()
        
        # Вставляем только новые транзакции (по transaction_id)
        cur.execute("""
            INSERT INTO dwh.DWH_FACT_TRANSACTIONS (
                transaction_id, transaction_date, amount, card_num,
                oper_type, oper_result, terminal_id
            )
            SELECT 
                transaction_id,
                transaction_date,
                amount,
                card_num,
                oper_type,
                oper_result,
                terminal
            FROM dwh.STG_TRANSACTIONS s
            WHERE NOT EXISTS (
                SELECT 1 FROM dwh.DWH_FACT_TRANSACTIONS f
                WHERE f.transaction_id = s.transaction_id
            );
        """)
        
        inserted_count = cur.rowcount
        conn.commit()
        cur.close()
        
        print(f"  Добавлено новых транзакций: {inserted_count}")
        return True
        
    except Exception as e:
        print(f"  Ошибка при загрузке транзакций: {e}")
        conn.rollback()
        return False

# ============================================
# 6. Функции выявления мошенничеств
# ============================================
def detect_fraud(conn, report_dt, target_date):
    """Выявляет мошеннические операции по 4 правилам"""
    try:
        print(f"\nПоиск мошеннических операций за {target_date}")
        
        cur = conn.cursor()
        
        # Очищаем отчет за эту дату (чтобы не дублировать)
        cur.execute("DELETE FROM dwh.REP_FRAUD WHERE DATE(event_dt) = %s", (target_date,))
        
        # ============================================
        # Правило 1: Просроченный или заблокированный паспорт
        # ============================================
        cur.execute("""
            INSERT INTO dwh.REP_FRAUD (event_dt, passport, fio, phone, event_type, report_dt)
            SELECT DISTINCT
                f.transaction_date,
                cl.passport_num,
                cl.last_name || ' ' || cl.first_name || ' ' || COALESCE(cl.patronymic, '') AS fio,
                cl.phone,
                'Просроченный или заблокированный паспорт',
                %s
            FROM dwh.DWH_FACT_TRANSACTIONS f
            LEFT JOIN dwh.DWH_DIM_CARDS_HIST c 
                ON f.card_num = c.card_num 
                AND f.transaction_date >= c.effective_from 
                AND (c.effective_to IS NULL OR f.transaction_date < c.effective_to)
            LEFT JOIN dwh.DWH_DIM_ACCOUNTS_HIST a 
                ON c.account_num = a.account_num 
                AND f.transaction_date >= a.effective_from 
                AND (a.effective_to IS NULL OR f.transaction_date < a.effective_to)
            LEFT JOIN dwh.DWH_DIM_CLIENTS_HIST cl 
                ON a.client_id = cl.client_id 
                AND f.transaction_date >= cl.effective_from 
                AND (cl.effective_to IS NULL OR f.transaction_date < cl.effective_to)
            WHERE DATE(f.transaction_date) = %s
            AND (
                cl.passport_num IN (
                    SELECT passport_num FROM dwh.DWH_FACT_PASSPORT_BLACKLIST
                )
                OR (cl.passport_valid_to IS NOT NULL AND cl.passport_valid_to < DATE(f.transaction_date))
            );
        """, (report_dt, target_date))
        
        rule1_count = cur.rowcount
        
        # ============================================
        # Правило 2: Недействующий договор
        # ============================================
        cur.execute("""
            INSERT INTO dwh.REP_FRAUD (event_dt, passport, fio, phone, event_type, report_dt)
            SELECT DISTINCT
                f.transaction_date,
                cl.passport_num,
                cl.last_name || ' ' || cl.first_name || ' ' || COALESCE(cl.patronymic, '') AS fio,
                cl.phone,
                'Недействующий договор',
                %s
            FROM dwh.DWH_FACT_TRANSACTIONS f
            LEFT JOIN dwh.DWH_DIM_CARDS_HIST c 
                ON f.card_num = c.card_num 
                AND f.transaction_date >= c.effective_from 
                AND (c.effective_to IS NULL OR f.transaction_date < c.effective_to)
            LEFT JOIN dwh.DWH_DIM_ACCOUNTS_HIST a 
                ON c.account_num = a.account_num 
                AND f.transaction_date >= a.effective_from 
                AND (a.effective_to IS NULL OR f.transaction_date < a.effective_to)
            LEFT JOIN dwh.DWH_DIM_CLIENTS_HIST cl 
                ON a.client_id = cl.client_id 
                AND f.transaction_date >= cl.effective_from 
                AND (cl.effective_to IS NULL OR f.transaction_date < cl.effective_to)
            WHERE DATE(f.transaction_date) = %s
            AND a.valid_to < DATE(f.transaction_date);
        """, (report_dt, target_date))
        
        rule2_count = cur.rowcount
        
        # ============================================
        # Правило 3: Операции в разных городах за 1 час
        # ============================================
        cur.execute("""
            INSERT INTO dwh.REP_FRAUD (event_dt, passport, fio, phone, event_type, report_dt)
            WITH client_transactions AS (
                SELECT 
                    f.transaction_id,
                    f.transaction_date,
                    cl.passport_num,
                    cl.last_name || ' ' || cl.first_name || ' ' || COALESCE(cl.patronymic, '') AS fio,
                    cl.phone,
                    t.terminal_city
                FROM dwh.DWH_FACT_TRANSACTIONS f
                LEFT JOIN dwh.DWH_DIM_CARDS_HIST c 
                    ON f.card_num = c.card_num 
                    AND f.transaction_date >= c.effective_from 
                    AND (c.effective_to IS NULL OR f.transaction_date < c.effective_to)
                LEFT JOIN dwh.DWH_DIM_ACCOUNTS_HIST a 
                    ON c.account_num = a.account_num 
                    AND f.transaction_date >= a.effective_from 
                    AND (a.effective_to IS NULL OR f.transaction_date < a.effective_to)
                LEFT JOIN dwh.DWH_DIM_CLIENTS_HIST cl 
                    ON a.client_id = cl.client_id 
                    AND f.transaction_date >= cl.effective_from 
                    AND (cl.effective_to IS NULL OR f.transaction_date < cl.effective_to)
                LEFT JOIN dwh.DWH_DIM_TERMINALS_HIST t 
                    ON f.terminal_id = t.terminal_id 
                    AND f.transaction_date >= t.effective_from 
                    AND (t.effective_to IS NULL OR f.transaction_date < t.effective_to)
                WHERE DATE(f.transaction_date) = %s
            ),
            diff_cities AS (
                SELECT 
                    v2.transaction_date as event_dt,
                    v1.passport_num,
                    v1.fio,
                    v1.phone
                FROM client_transactions v1
                JOIN client_transactions v2 
                    ON v1.passport_num = v2.passport_num
                    AND v1.transaction_id != v2.transaction_id
                    AND v1.terminal_city != v2.terminal_city
                    AND ABS(EXTRACT(EPOCH FROM (v2.transaction_date - v1.transaction_date))) < 3600
                WHERE v1.terminal_city IS NOT NULL 
                    AND v2.terminal_city IS NOT NULL
                    AND v1.passport_num IS NOT NULL
            )
            SELECT DISTINCT event_dt, passport_num, fio, phone, 
                   'Операции в разных городах за 1 час',
                   %s
            FROM diff_cities;
        """, (target_date, report_dt))
        
        rule3_count = cur.rowcount
        
        # ============================================
        # Правило 4: Подбор суммы
        # ============================================
        cur.execute("""
            INSERT INTO dwh.REP_FRAUD (event_dt, passport, fio, phone, event_type, report_dt)
            WITH ranked_transactions AS (
                SELECT 
                    f.transaction_date,
                    f.amount,
                    f.oper_result,
                    f.card_num,
                    cl.passport_num,
                    cl.last_name || ' ' || cl.first_name || ' ' || COALESCE(cl.patronymic, '') AS fio,
                    cl.phone,
                    LAG(f.amount) OVER (PARTITION BY f.card_num ORDER BY f.transaction_date) as prev_amount,
                    LAG(f.oper_result) OVER (PARTITION BY f.card_num ORDER BY f.transaction_date) as prev_result,
                    LAG(f.transaction_date) OVER (PARTITION BY f.card_num ORDER BY f.transaction_date) as prev_date,
                    COUNT(*) OVER (PARTITION BY f.card_num ORDER BY f.transaction_date 
                                   RANGE BETWEEN INTERVAL '20 minutes' PRECEDING AND CURRENT ROW) as attempts_20min
                FROM dwh.DWH_FACT_TRANSACTIONS f
                LEFT JOIN dwh.DWH_DIM_CARDS_HIST c 
                    ON f.card_num = c.card_num 
                    AND f.transaction_date >= c.effective_from 
                    AND (c.effective_to IS NULL OR f.transaction_date < c.effective_to)
                LEFT JOIN dwh.DWH_DIM_ACCOUNTS_HIST a 
                    ON c.account_num = a.account_num 
                    AND f.transaction_date >= a.effective_from 
                    AND (a.effective_to IS NULL OR f.transaction_date < a.effective_to)
                LEFT JOIN dwh.DWH_DIM_CLIENTS_HIST cl 
                    ON a.client_id = cl.client_id 
                    AND f.transaction_date >= cl.effective_from 
                    AND (cl.effective_to IS NULL OR f.transaction_date < cl.effective_to)
                WHERE DATE(f.transaction_date) = %s
            ),
            fraud_pattern AS (
                SELECT 
                    transaction_date,
                    passport_num,
                    fio,
                    phone
                FROM ranked_transactions
                WHERE oper_result = 'SUCCESS'
                    AND attempts_20min > 3
                    AND prev_result = 'REJECT'
                    AND amount < prev_amount
                    AND EXTRACT(EPOCH FROM (transaction_date - prev_date)) < 1200
                    AND passport_num IS NOT NULL
            )
            SELECT DISTINCT transaction_date, passport_num, fio, phone,
                   'Подбор суммы (успешная после 3+ отклоненных за 20 мин)',
                   %s
            FROM fraud_pattern;
        """, (target_date, report_dt))
        
        rule4_count = cur.rowcount
        
        conn.commit()
        
        print(f"\n  Результаты отчета за {target_date}:")
        print(f"    Правило 1 (просроченный паспорт): {rule1_count}")
        print(f"    Правило 2 (недействующий договор): {rule2_count}")
        print(f"    Правило 3 (разные города): {rule3_count}")
        print(f"    Правило 4 (подбор суммы): {rule4_count}")
        print(f"    ВСЕГО: {rule1_count + rule2_count + rule3_count + rule4_count}")
        
        cur.close()
        return True
        
    except Exception as e:
        print(f"  Ошибка при поиске мошенничеств: {e}")
        conn.rollback()
        return False

# ============================================
# 7. Основной процесс ETL
# ============================================
def run_etl_process(reset_metadata=False):
    """Основная функция ETL процесса"""
    
    print("\n" + "="*60)
    print("ЗАПУСК ETL ПРОЦЕССА")
    print("="*60)
    
    # Подключаемся к БД
    conn = get_connection()
    if not conn:
        return False
    
    try:
        # Инициализируем менеджер метаданных
        meta_mgr = MetadataManager(conn)
        
        # Находим все файлы для обработки
        files_to_process = find_files_to_process()
        
        if not files_to_process:
            print("Нет файлов для обработки")
            return True
        
        print(f"Найдено файлов для обработки: {len(files_to_process)}")
        
        # Если нужно сбросить метаданные
        if reset_metadata:
            print("\nСброс метаданных для всех файлов...")
            for file_path in files_to_process:
                file_name = os.path.basename(file_path)
                meta_mgr.reset_file_status(file_name)
        
        # Группируем файлы по датам
        files_by_date = {}
        for file_path in files_to_process:
            file_name = os.path.basename(file_path)
            file_date = extract_date_from_filename(file_name)
            
            if file_date:
                if file_date not in files_by_date:
                    files_by_date[file_date] = []
                files_by_date[file_date].append(file_path)
            else:
                print(f"Не удалось извлечь дату из имени файла: {file_name}")
        
        if not files_by_date:
            print("Не найдено файлов с корректными датами")
            return True
        
        # Обрабатываем файлы по датам (от старых к новым)
        processed_dates = []
        for load_date in sorted(files_by_date.keys()):
            print(f"\n{'='*60}")
            print(f"ОБРАБОТКА ДАТЫ: {load_date}")
            print(f"{'='*60}")
            
            date_files = files_by_date[load_date]
            has_transactions = False
            
            for file_path in date_files:
                file_name = os.path.basename(file_path)
                
                # Проверяем, не обработан ли файл
                if not reset_metadata and meta_mgr.is_file_processed(file_name):
                    print(f"Файл {file_name} уже обработан, пропускаем")
                    continue
                
                print(f"\n--- Обработка файла: {file_name} ---")
                
                try:
                    rows_loaded = 0
                    
                    # Определяем тип файла и загружаем
                    if 'transactions' in file_name.lower():
                        rows_loaded = load_transactions_to_stg(file_path, conn, load_date)
                        if rows_loaded > 0:
                            if load_transactions_to_fact(conn):
                                has_transactions = True
                                print(f"  ✓ Транзакции за {load_date} успешно загружены")
                        else:
                            print(f"  ⚠ Нет транзакций за {load_date}")
                    
                    elif 'terminals' in file_name.lower():
                        rows_loaded = load_terminals_to_stg(file_path, conn)
                        if load_terminals_to_dim_hist(conn, load_date):
                            print(f"  ✓ Терминалы за {load_date} успешно загружены")
                    
                    elif 'passport_blacklist' in file_name.lower():
                        rows_loaded = load_blacklist_to_stg(file_path, conn)
                        if load_blacklist_to_fact(conn):
                            print(f"  ✓ Черный список за {load_date} успешно загружен")
                    
                    # Отмечаем файл как обработанный в метаданных
                    if rows_loaded > 0 or 'passport_blacklist' in file_name.lower() or 'terminals' in file_name.lower():
                        meta_mgr.mark_file_processed(file_name, load_date, rows_loaded, 'SUCCESS')
                    
                    # Архивация файла
                    archive_file(file_path)
                    
                except Exception as e:
                    print(f"  ✗ Ошибка при обработке {file_name}: {e}")
                    meta_mgr.mark_file_processed(file_name, load_date, 0, 'ERROR', str(e))
            
            # Если были транзакции за эту дату, строим отчет
            if has_transactions:
                print(f"\n--- Формирование отчета за {load_date} ---")
                if detect_fraud(conn, datetime.now(), load_date):
                    print(f"  ✓ Отчет за {load_date} успешно сформирован")
                    processed_dates.append(load_date)
        
        print(f"\n{'='*60}")
        print("ETL ПРОЦЕСС ЗАВЕРШЕН")
        if processed_dates:
            print(f"Обработаны даты с транзакциями: {', '.join(str(d) for d in processed_dates)}")
        else:
            print("Не обработано ни одной даты с транзакциями")
        print(f"{'='*60}")
        
        return True
        
    except Exception as e:
        print(f"Критическая ошибка в ETL процессе: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# ============================================
# 8. Точка входа
# ============================================
if __name__ == "__main__":
    print("="*60)
    print("ЗАПУСК ETL ПРОЦЕССА")
    print("="*60)
    print(f"Текущая директория: {os.getcwd()}")
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"DATA_DIR: {DATA_DIR}")
    print(f"ARCHIVE_DIR: {ARCHIVE_DIR}")
    
    # Проверяем наличие файлов в data директории
    print(f"\nСодержимое {DATA_DIR}:")
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            print(f"  - {f}")
    else:
        print(f"  Директория {DATA_DIR} не существует")
    
    # Запускаем ETL с сбросом метаданных
    success = run_etl_process(reset_metadata=True)
    
    if success:
        print("\n✓ ETL процесс завершен успешно")
    else:
        print("\n✗ ETL процесс завершен с ошибками")
        exit(1)