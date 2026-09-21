import os, glob, sys
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime

logs = glob.glob('logs/*.log')
cutoff = datetime(2026, 9, 10, 0, 0, 0)

recent_logs = []
for l in logs:
    mtime = datetime.fromtimestamp(os.path.getmtime(l))
    if mtime >= cutoff:
        recent_logs.append((l, mtime, os.path.getsize(l)))

recent_logs.sort(key=lambda x: x[1], reverse=True)

print("\n--- HATA / EXCEPTION TARAMASI (Son 7 Gün) ---")
error_lines = []
for l, _, _ in recent_logs:
    try:
        with open(l, 'r', encoding='utf-8', errors='ignore') as f:
            for line_no, line in enumerate(f, 1):
                ll = line.lower()
                if any(err_kw in ll for err_kw in ['error', 'exception', 'traceback', 'critical', 'failed']):
                    if '0 error' in ll or 'error_score' in ll or 'errors: 0' in ll:
                        continue
                    error_lines.append((os.path.basename(l), line_no, line.strip()))
    except Exception:
        pass

print(f"Toplam Hata / Exception Satırı: {len(error_lines)}")
for f, l_no, line in error_lines:
    print(f"[{f}:{l_no}] {line}")

print("\n--- SON TELEGRAM BİLDİRİMİ İÇERİĞİ ---")
# Let's find the exact notification text sent in paper_trading_service_v4.log or paper_trading_service.log
for log_name in ["logs/paper_trading_service_v4.log", "logs/paper_trading_service.log"]:
    if os.path.exists(log_name):
        with open(log_name, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            print(f"\n--- Son 20 satır ({log_name}) ---")
            for l in lines[-20:]:
                print(l.strip())
