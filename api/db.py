import sqlite3
import time
import os
from datetime import datetime, timezone

DB_PATH = "data/usage.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_usage (
            user_id TEXT PRIMARY KEY,
            plan TEXT,
            total_tokens INTEGER DEFAULT 0,
            api_calls_count INTEGER DEFAULT 0,
            api_window_start REAL DEFAULT 0,
            emails_sent_count INTEGER DEFAULT 0,
            emails_last_sent_date TEXT DEFAULT ''
        )
    ''')
    
    # Migration for new column
    try:
        c.execute("ALTER TABLE user_usage ADD COLUMN tokens_last_reset_date TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass # Column already exists

    conn.commit()
    conn.close()

def get_or_create_user(conn, user_id, current_plan):
    c = conn.cursor()
    c.execute("SELECT * FROM user_usage WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if row is None:
        c.execute('''
            INSERT INTO user_usage (user_id, plan, api_window_start, tokens_last_reset_date) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, current_plan, time.time(), datetime.now(timezone.utc).strftime("%Y-%m")))
        conn.commit()
        return get_user(conn, user_id)
    
    # Check for plan change (upgrade/downgrade)
    db_plan = row["plan"]
    if db_plan != current_plan:
        # Reset counters on plan change
        c.execute('''
            UPDATE user_usage 
            SET plan = ?, api_calls_count = 0, emails_sent_count = 0 
            WHERE user_id = ?
        ''', (current_plan, user_id))
        conn.commit()
        return get_user(conn, user_id)
        
    return row

def get_user(conn, user_id):
    c = conn.cursor()
    c.execute("SELECT * FROM user_usage WHERE user_id = ?", (user_id,))
    return c.fetchone()

def check_and_increment_api_call(user_id, plan):
    conn = get_db()
    try:
        user = get_or_create_user(conn, user_id, plan)
        
        limit = 5 if "premium" in plan else 1
        now = time.time()
        window_start = user["api_window_start"]
        count = user["api_calls_count"]
        
        # Reset window if > 60s
        if now - window_start > 60:
            count = 0
            window_start = now
            conn.execute('''
                UPDATE user_usage 
                SET api_calls_count = 0, api_window_start = ? 
                WHERE user_id = ?
            ''', (window_start, user_id))
            
        if count >= limit:
            return False, f"API rate limit exceeded. Limit: {limit}/min."
            
        conn.execute('''
            UPDATE user_usage 
            SET api_calls_count = api_calls_count + 1 
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        return True, None
    finally:
        conn.close()

def check_and_increment_email(user_id, plan):
    conn = get_db()
    try:
        user = get_or_create_user(conn, user_id, plan)
        
        # Free users get 0 emails
        limit = 10 if "premium" in plan else 0
        if limit == 0:
             return False, "Email sending is a Premium feature."

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        last_date = user["emails_last_sent_date"]
        count = user["emails_sent_count"]
        
        # Reset daily quota
        if last_date != today:
            count = 0
            conn.execute('''
                UPDATE user_usage 
                SET emails_sent_count = 0, emails_last_sent_date = ? 
                WHERE user_id = ?
            ''', (today, user_id))
            
        if count >= limit:
            return False, f"Daily email limit exceeded. Limit: {limit}/day."
            
        conn.execute('''
            UPDATE user_usage 
            SET emails_sent_count = emails_sent_count + 1, emails_last_sent_date = ?
            WHERE user_id = ?
        ''', (today, user_id))
        conn.commit()
        return True, None
    finally:
        conn.close()

def track_token_usage(user_id, tokens):
    conn = get_db()
    try:
        # Check for monthly reset
        c = conn.cursor()
        c.execute("SELECT tokens_last_reset_date FROM user_usage WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        last_month = row["tokens_last_reset_date"] if row and "tokens_last_reset_date" in row.keys() else ""
        
        if last_month != current_month:
            conn.execute('''
                UPDATE user_usage 
                SET total_tokens = ?, tokens_last_reset_date = ?
                WHERE user_id = ?
            ''', (tokens, current_month, user_id))
        else:
            conn.execute('''
                UPDATE user_usage 
                SET total_tokens = total_tokens + ? 
                WHERE user_id = ?
            ''', (tokens, user_id))
            
        conn.commit()
    finally:
        conn.close()

def get_user_stats(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM user_usage WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row:
            return {"total_tokens": 0, "api_calls_count": 0, "emails_sent_count": 0}
            
        # Lazy update for view: check if API window expired
        now = time.time()
        window_start = row["api_window_start"]
        api_count = row["api_calls_count"]
        
        if now - window_start > 60 and api_count > 0:
            # It expired, so for display purposes (and DB consistency), reset it
            conn.execute('''
                UPDATE user_usage 
                SET api_calls_count = 0, api_window_start = ? 
                WHERE user_id = ?
            ''', (now, user_id))
            conn.commit()
            api_count = 0
            
        return {
            "total_tokens": row["total_tokens"], 
            "api_calls_count": api_count, 
            "emails_sent_count": row["emails_sent_count"]
        }
    finally:
        conn.close()
