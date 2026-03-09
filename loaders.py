import pandas as pd
import os

# ============================================
# Загрузка в STG (сырые данные)
# ============================================
def load_transactions_to_stg(file_path, conn, load_date):
    """Загружает CSV-файл с транзакциями в STG_TRANSACTIONS"""
    try:
        print(f"\nЗагрузка транзакций: {os.path.basename(file_path)}")
        
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
        cur.execute("TRUNCATE TABLE dwh.STG_TRANSACTIONS;")
        
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
# Загрузка в DWH (витрины)
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
        
        # Добавляем новые версии терминалов
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