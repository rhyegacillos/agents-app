import sqlite3
import time
import os
import json
from datetime import datetime, timezone

DB_PATH = "data/usage.db"

TOKEN_LIMIT_FREE = int(os.getenv("TOKEN_LIMIT_FREE", "50000"))
TOKEN_LIMIT_PREMIUM = int(os.getenv("TOKEN_LIMIT_PREMIUM", "500000"))

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

    c.execute('''
        CREATE TABLE IF NOT EXISTS saved_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            created_at TEXT,
            industry TEXT,
            tone TEXT,
            constraints_json TEXT,
            models_json TEXT,
            results_json TEXT,
            rank_result_json TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS saved_rank_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            created_at TEXT,
            run_ids_key TEXT,
            run_ids_json TEXT,
            report_json TEXT,
            runs_json TEXT,
            model TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS saved_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            created_at TEXT,
            run_a_id INTEGER,
            run_b_id INTEGER,
            winner_run_id INTEGER,
            comparison_json TEXT,
            model TEXT
        )
    ''')
    
    # Migration for new column
    try:
        c.execute("ALTER TABLE user_usage ADD COLUMN tokens_last_reset_date TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass # Column already exists
    try:
        c.execute("ALTER TABLE saved_results ADD COLUMN rank_result_json TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE saved_rank_reports ADD COLUMN runs_json TEXT")
    except sqlite3.OperationalError:
        pass
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

def get_token_limit(plan):
    return TOKEN_LIMIT_PREMIUM if "premium" in plan else TOKEN_LIMIT_FREE


def check_token_limit(user_id, plan):
    conn = get_db()
    try:
        user = get_or_create_user(conn, user_id, plan)

        last_month = user["tokens_last_reset_date"] if "tokens_last_reset_date" in user.keys() else ""
        total_tokens = user["total_tokens"] or 0
        did_reset, _ = _reset_tokens_if_new_month(conn, user_id, last_month)
        if did_reset:
            total_tokens = 0

        token_limit = get_token_limit(plan)
        if total_tokens >= token_limit:
            return False, f"Monthly token limit exceeded. Limit: {token_limit} tokens."
        return True, None
    finally:
        conn.close()

def _reset_tokens_if_new_month(conn, user_id, last_month):
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    if last_month != current_month:
        conn.execute('''
            UPDATE user_usage 
            SET total_tokens = 0, tokens_last_reset_date = ?
            WHERE user_id = ?
        ''', (current_month, user_id))
        conn.commit()
        return True, current_month
    return False, current_month

def check_and_increment_api_call(user_id, plan):
    conn = get_db()
    try:
        user = get_or_create_user(conn, user_id, plan)
        
        last_month = user["tokens_last_reset_date"] if "tokens_last_reset_date" in user.keys() else ""
        total_tokens = user["total_tokens"] or 0
        did_reset, _ = _reset_tokens_if_new_month(conn, user_id, last_month)
        if did_reset:
            total_tokens = 0

        token_limit = get_token_limit(plan)
        if total_tokens >= token_limit:
            return False, f"Monthly token limit exceeded. Limit: {token_limit} tokens."

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
            
        last_month = row["tokens_last_reset_date"] if "tokens_last_reset_date" in row.keys() else ""
        total_tokens = row["total_tokens"] or 0
        did_reset, _ = _reset_tokens_if_new_month(conn, user_id, last_month)
        if did_reset:
            total_tokens = 0

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
            "total_tokens": total_tokens, 
            "api_calls_count": api_count, 
            "emails_sent_count": row["emails_sent_count"]
        }
    finally:
        conn.close()

def save_results(user_id, industry, tone, constraints, models, results, rank_result=None):
    conn = get_db()
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        c = conn.cursor()
        c.execute('''
            INSERT INTO saved_results (
                user_id, created_at, industry, tone, constraints_json, models_json, results_json, rank_result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            created_at,
            industry,
            tone,
            json.dumps(constraints or []),
            json.dumps(models or []),
            json.dumps(results or {}),
            json.dumps(rank_result) if rank_result is not None else None,
        ))
        conn.commit()
        return {"id": c.lastrowid, "created_at": created_at}
    finally:
        conn.close()

def list_saved_results(user_id, limit=10):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT id, created_at, industry, tone, constraints_json, models_json
            FROM saved_results
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = c.fetchall()
        out = []
        for row in rows:
            models = []
            constraints = []
            if row["models_json"]:
                try:
                    models = json.loads(row["models_json"])
                except json.JSONDecodeError:
                    models = []
            if row["constraints_json"]:
                try:
                    constraints = json.loads(row["constraints_json"])
                except json.JSONDecodeError:
                    constraints = []
            out.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "industry": row["industry"],
                "tone": row["tone"],
                "constraints": constraints,
                "models": models,
                "model_count": len(models) if isinstance(models, list) else 0,
            })
        return out
    finally:
        conn.close()


def list_saved_results_full(user_id, limit=None):
    conn = get_db()
    try:
        c = conn.cursor()
        if limit is None:
            c.execute('''
                SELECT id, created_at, industry, tone, constraints_json, models_json, results_json, rank_result_json
                FROM saved_results
                WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))
        else:
            c.execute('''
                SELECT id, created_at, industry, tone, constraints_json, models_json, results_json, rank_result_json
                FROM saved_results
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
        rows = c.fetchall()
        out = []
        for row in rows:
            try:
                constraints = json.loads(row["constraints_json"]) if row["constraints_json"] else []
            except json.JSONDecodeError:
                constraints = []
            try:
                models = json.loads(row["models_json"]) if row["models_json"] else []
            except json.JSONDecodeError:
                models = []
            try:
                results = json.loads(row["results_json"]) if row["results_json"] else {}
            except json.JSONDecodeError:
                results = {}
            try:
                rank_result = json.loads(row["rank_result_json"]) if row["rank_result_json"] else None
            except json.JSONDecodeError:
                rank_result = None
            out.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "industry": row["industry"],
                "tone": row["tone"],
                "constraints": constraints,
                "models": models,
                "results": results,
                "rank_result": rank_result,
            })
        return out
    finally:
        conn.close()

def get_saved_result(user_id, saved_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT id, created_at, industry, tone, constraints_json, models_json, results_json, rank_result_json
            FROM saved_results
            WHERE id = ? AND user_id = ?
        ''', (saved_id, user_id))
        row = c.fetchone()
        if not row:
            return None
        try:
            constraints = json.loads(row["constraints_json"]) if row["constraints_json"] else []
        except json.JSONDecodeError:
            constraints = []
        try:
            models = json.loads(row["models_json"]) if row["models_json"] else []
        except json.JSONDecodeError:
            models = []
        try:
            results = json.loads(row["results_json"]) if row["results_json"] else {}
        except json.JSONDecodeError:
            results = {}
        try:
            rank_result = json.loads(row["rank_result_json"]) if row["rank_result_json"] else None
        except json.JSONDecodeError:
            rank_result = None
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "industry": row["industry"],
            "tone": row["tone"],
            "constraints": constraints,
            "models": models,
            "results": results,
            "rank_result": rank_result,
        }
    finally:
        conn.close()

def get_saved_rank_report(user_id, run_ids_key):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT *
            FROM saved_rank_reports
            WHERE user_id = ? AND run_ids_key = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (user_id, run_ids_key))
        row = c.fetchone()
        if not row:
            return None
        report = {}
        if row["report_json"]:
            try:
                report = json.loads(row["report_json"])
            except json.JSONDecodeError:
                report = {}
        run_ids = []
        if row["run_ids_json"]:
            try:
                run_ids = json.loads(row["run_ids_json"])
            except json.JSONDecodeError:
                run_ids = []
        runs_snapshot = []
        if "runs_json" in row.keys() and row["runs_json"]:
            try:
                runs_snapshot = json.loads(row["runs_json"]) or []
            except json.JSONDecodeError:
                runs_snapshot = []
        if not run_ids and runs_snapshot:
            for run in runs_snapshot:
                try:
                    run_ids.append(int(run.get("id")))
                except (TypeError, ValueError, AttributeError):
                    continue
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "run_ids": run_ids,
            "run_ids_key": row["run_ids_key"],
            "report": report,
            "runs_snapshot": runs_snapshot,
            "model": row["model"],
        }
    finally:
        conn.close()

def save_rank_report(
    user_id,
    run_ids_key,
    run_ids,
    report,
    model,
    runs_snapshot=None,
):
    conn = get_db()
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        c = conn.cursor()
        c.execute('''
            INSERT INTO saved_rank_reports (
                user_id, created_at, run_ids_key, run_ids_json, report_json, runs_json, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            created_at,
            run_ids_key,
            json.dumps(run_ids or []),
            json.dumps(report or {}),
            json.dumps(runs_snapshot or []),
            model,
        ))
        conn.commit()
        return {"id": c.lastrowid, "created_at": created_at}
    finally:
        conn.close()

def get_saved_rank_report_by_id(user_id, report_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT *
            FROM saved_rank_reports
            WHERE user_id = ? AND id = ?
            LIMIT 1
        ''', (user_id, report_id))
        row = c.fetchone()
        if not row:
            return None
        report = {}
        if row["report_json"]:
            try:
                report = json.loads(row["report_json"])
            except json.JSONDecodeError:
                report = {}
        run_ids = []
        if row["run_ids_json"]:
            try:
                run_ids = json.loads(row["run_ids_json"])
            except json.JSONDecodeError:
                run_ids = []
        runs_snapshot = []
        if "runs_json" in row.keys() and row["runs_json"]:
            try:
                runs_snapshot = json.loads(row["runs_json"]) or []
            except json.JSONDecodeError:
                runs_snapshot = []
        if not run_ids and runs_snapshot:
            for run in runs_snapshot:
                try:
                    run_ids.append(int(run.get("id")))
                except (TypeError, ValueError, AttributeError):
                    continue
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "run_ids": run_ids,
            "run_ids_key": row["run_ids_key"],
            "report": report,
            "runs_snapshot": runs_snapshot,
            "model": row["model"],
        }
    finally:
        conn.close()

def delete_saved_rank_report(user_id, report_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            DELETE FROM saved_rank_reports
            WHERE user_id = ? AND id = ?
        ''', (user_id, report_id))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()

def list_saved_rank_reports(user_id, limit=6):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT id, created_at, run_ids_json, report_json, runs_json, model
            FROM saved_rank_reports
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = c.fetchall()
        out = []
        for row in rows:
            run_ids = []
            if row["run_ids_json"]:
                try:
                    run_ids = json.loads(row["run_ids_json"])
                except json.JSONDecodeError:
                    run_ids = []
            runs_snapshot = []
            if "runs_json" in row.keys() and row["runs_json"]:
                try:
                    runs_snapshot = json.loads(row["runs_json"]) or []
                except json.JSONDecodeError:
                    runs_snapshot = []
            if not run_ids and runs_snapshot:
                for run in runs_snapshot:
                    try:
                        run_ids.append(int(run.get("id")))
                    except (TypeError, ValueError, AttributeError):
                        continue
            cleaned_run_ids = []
            for run_id in run_ids:
                try:
                    cleaned_run_ids.append(int(run_id))
                except (TypeError, ValueError):
                    continue
            run_ids = cleaned_run_ids
            report = {}
            if row["report_json"]:
                try:
                    report = json.loads(row["report_json"])
                except json.JSONDecodeError:
                    report = {}
            summary = str(report.get("summary", "") or "")
            ranked_runs = report.get("ranked_runs", []) or []
            top_run_id = None
            if isinstance(ranked_runs, list) and ranked_runs:
                try:
                    top_run_id = int(ranked_runs[0].get("run_id"))
                except (TypeError, ValueError):
                    top_run_id = None
            out.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "run_ids": run_ids,
                "summary": summary,
                "top_run_id": top_run_id,
                "model": row["model"],
            })
        return out
    finally:
        conn.close()

def update_rank_report_snapshot(
    user_id,
    report_id,
    runs_snapshot=None,
):
    fields = []
    params = []
    if runs_snapshot is not None:
        fields.append("runs_json = ?")
        params.append(json.dumps(runs_snapshot))
    if not fields:
        return False
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            f'''
            UPDATE saved_rank_reports
            SET {", ".join(fields)}
            WHERE user_id = ? AND id = ?
            ''',
            (*params, user_id, report_id),
        )
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()

def get_saved_results_by_ids(user_id, ids):
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            f'''
            SELECT id, created_at, industry, tone, constraints_json, models_json, results_json
            FROM saved_results
            WHERE user_id = ? AND id IN ({placeholders})
            ''',
            (user_id, *ids),
        )
        rows = c.fetchall()
        out = []
        for row in rows:
            try:
                constraints = json.loads(row["constraints_json"]) if row["constraints_json"] else []
            except json.JSONDecodeError:
                constraints = []
            try:
                models = json.loads(row["models_json"]) if row["models_json"] else []
            except json.JSONDecodeError:
                models = []
            try:
                results = json.loads(row["results_json"]) if row["results_json"] else {}
            except json.JSONDecodeError:
                results = {}
            out.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "industry": row["industry"],
                "tone": row["tone"],
                "constraints": constraints,
                "models": models,
                "results": results,
            })
        return out
    finally:
        conn.close()

def get_saved_comparison(user_id, run_a_id, run_b_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT *
            FROM saved_comparisons
            WHERE user_id = ?
              AND ((run_a_id = ? AND run_b_id = ?) OR (run_a_id = ? AND run_b_id = ?))
            ORDER BY created_at DESC
            LIMIT 1
        ''', (user_id, run_a_id, run_b_id, run_b_id, run_a_id))
        row = c.fetchone()
        if not row:
            return None
        comparison = {}
        if row["comparison_json"]:
            try:
                comparison = json.loads(row["comparison_json"])
            except json.JSONDecodeError:
                comparison = {}
        winner_run_id = row["winner_run_id"]
        if winner_run_id == run_a_id:
            winner = "A"
        elif winner_run_id == run_b_id:
            winner = "B"
        else:
            winner = "tie"
        comparison["winner"] = winner
        return {
            "comparison_id": row["id"],
            "created_at": row["created_at"],
            "run_a_id": row["run_a_id"],
            "run_b_id": row["run_b_id"],
            "winner_run_id": winner_run_id,
            "comparison": comparison,
            "cached": True,
        }
    finally:
        conn.close()

def get_saved_comparison_by_id(user_id, comparison_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT *
            FROM saved_comparisons
            WHERE user_id = ? AND id = ?
            LIMIT 1
        ''', (user_id, comparison_id))
        row = c.fetchone()
        if not row:
            return None
        comparison = {}
        if row["comparison_json"]:
            try:
                comparison = json.loads(row["comparison_json"])
            except json.JSONDecodeError:
                comparison = {}
        return {
            "comparison_id": row["id"],
            "created_at": row["created_at"],
            "run_a_id": row["run_a_id"],
            "run_b_id": row["run_b_id"],
            "winner_run_id": row["winner_run_id"],
            "comparison": comparison,
            "cached": True,
        }
    finally:
        conn.close()

def delete_saved_comparison(user_id, comparison_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            DELETE FROM saved_comparisons
            WHERE user_id = ? AND id = ?
        ''', (user_id, comparison_id))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()

def save_comparison(user_id, run_a_id, run_b_id, winner_run_id, comparison, model):
    conn = get_db()
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        c = conn.cursor()
        c.execute('''
            INSERT INTO saved_comparisons (
                user_id, created_at, run_a_id, run_b_id, winner_run_id, comparison_json, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            created_at,
            run_a_id,
            run_b_id,
            winner_run_id,
            json.dumps(comparison or {}),
            model,
        ))
        conn.commit()
        return {"id": c.lastrowid, "created_at": created_at}
    finally:
        conn.close()

def list_saved_comparisons(user_id, limit=8):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT id, created_at, run_a_id, run_b_id, winner_run_id, comparison_json
            FROM saved_comparisons
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = c.fetchall()
        out = []
        for row in rows:
            top_outputs = None
            if row["comparison_json"]:
                try:
                    comparison = json.loads(row["comparison_json"])
                    top_outputs = comparison.get("top_outputs")
                except json.JSONDecodeError:
                    top_outputs = None
            out.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "run_a_id": row["run_a_id"],
                "run_b_id": row["run_b_id"],
                "winner_run_id": row["winner_run_id"],
                "top_outputs": top_outputs,
            })
        return out
    finally:
        conn.close()

def delete_saved_result(user_id, saved_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            DELETE FROM saved_results
            WHERE id = ? AND user_id = ?
        ''', (saved_id, user_id))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()


def update_saved_result_rank(user_id, saved_id, rank_result):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            UPDATE saved_results
            SET rank_result_json = ?
            WHERE id = ? AND user_id = ?
        ''', (json.dumps(rank_result or {}), saved_id, user_id))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()

def get_saved_results_usage_bytes(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT COALESCE(SUM(
                LENGTH(COALESCE(industry, '')) +
                LENGTH(COALESCE(tone, '')) +
                LENGTH(COALESCE(constraints_json, '')) +
                LENGTH(COALESCE(models_json, '')) +
                LENGTH(COALESCE(results_json, '')) +
                LENGTH(COALESCE(rank_result_json, ''))
            ), 0) AS total
            FROM saved_results
            WHERE user_id = ?
        ''', (user_id,))
        row = c.fetchone()
        return int(row["total"] or 0)
    finally:
        conn.close()
