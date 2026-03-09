import os
from datetime import datetime

from config import (
    BASE_DIR, DATA_DIR, ARCHIVE_DIR,
    get_connection, MetadataManager,
    find_files_to_process, extract_date_from_filename, archive_file
)
from loaders import (
    load_transactions_to_stg, load_terminals_to_stg, load_blacklist_to_stg,
    load_transactions_to_fact, load_terminals_to_dim_hist, load_blacklist_to_fact
)
from detectors import detect_fraud

def run_etl_process(reset_metadata=False):
    """Основная функция ETL процесса"""
    
    print("\n" + "="*60)
    print("ЗАПУСК ETL ПРОЦЕССА")
    print("="*60)
    
    conn = get_connection()
    if not conn:
        return False
    
    try:
        meta_mgr = MetadataManager(conn)
        files_to_process = find_files_to_process()
        
        if not files_to_process:
            print("Нет файлов для обработки")
            return True
        
        if reset_metadata:
            print("\nСброс метаданных для всех файлов...")
            for file_path in files_to_process:
                meta_mgr.reset_file_status(os.path.basename(file_path))
        
        # Группируем файлы по датам
        files_by_date = {}
        for file_path in files_to_process:
            file_name = os.path.basename(file_path)
            file_date = extract_date_from_filename(file_name)
            if file_date:
                files_by_date.setdefault(file_date, []).append(file_path)
        
        processed_dates = []
        for load_date in sorted(files_by_date.keys()):
            print(f"\n{'='*60}")
            print(f"ОБРАБОТКА ДАТЫ: {load_date}")
            print(f"{'='*60}")
            
            has_transactions = False
            
            for file_path in files_by_date[load_date]:
                file_name = os.path.basename(file_path)
                
                if not reset_metadata and meta_mgr.is_file_processed(file_name):
                    print(f"Файл {file_name} уже обработан, пропускаем")
                    continue
                
                print(f"\n--- Обработка файла: {file_name} ---")
                
                try:
                    rows_loaded = 0
                    
                    if 'transactions' in file_name.lower():
                        rows_loaded = load_transactions_to_stg(file_path, conn, load_date)
                        if rows_loaded > 0 and load_transactions_to_fact(conn):
                            has_transactions = True
                            print(f"  ✓ Транзакции за {load_date} успешно загружены")
                    
                    elif 'terminals' in file_name.lower():
                        rows_loaded = load_terminals_to_stg(file_path, conn)
                        if load_terminals_to_dim_hist(conn, load_date):
                            print(f"  ✓ Терминалы за {load_date} успешно загружены")
                    
                    elif 'passport_blacklist' in file_name.lower():
                        rows_loaded = load_blacklist_to_stg(file_path, conn)
                        if load_blacklist_to_fact(conn):
                            print(f"  ✓ Черный список за {load_date} успешно загружен")
                    
                    # Отмечаем файл как обработанный
                    if rows_loaded > 0 or any(x in file_name.lower() for x in ['passport_blacklist', 'terminals']):
                        meta_mgr.mark_file_processed(file_name, load_date, rows_loaded, 'SUCCESS')
                    
                    archive_file(file_path)
                    
                except Exception as e:
                    print(f"  ✗ Ошибка при обработке {file_name}: {e}")
                    meta_mgr.mark_file_processed(file_name, load_date, 0, 'ERROR', str(e))
            
            # Если были транзакции, строим отчет
            if has_transactions:
                print(f"\n--- Формирование отчета за {load_date} ---")
                if detect_fraud(conn, datetime.now(), load_date):
                    print(f"  ✓ Отчет за {load_date} успешно сформирован")
                    processed_dates.append(load_date)
        
        print(f"\n{'='*60}")
        print("ETL ПРОЦЕСС ЗАВЕРШЕН")
        return True
        
    finally:
        conn.close()

if __name__ == "__main__":
    print("="*60)
    print("ЗАПУСК ETL ПРОЦЕССА")
    print("="*60)
    print(f"DATA_DIR: {DATA_DIR}")
    print(f"ARCHIVE_DIR: {ARCHIVE_DIR}")
    
    success = run_etl_process(reset_metadata=True)
    
    if success:
        print("\n✓ ETL процесс завершен успешно")
    else:
        print("\n✗ ETL процесс завершен с ошибками")
        exit(1)