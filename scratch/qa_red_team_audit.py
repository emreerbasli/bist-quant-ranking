"""
scratch/qa_red_team_audit.py
================================================================================
KIDEMLİ QA & RED TEAM DERİN KANTİTATİF SİSTEM DENETÇİSİ (AST & REGEX AUDITOR)
================================================================================
Bu betik sistemdeki tüm .py, .bat ve konfigürasyon dosyalarını otonom olarak
tarayarak 4 kritik QA & Red Team güvenlik alanını denetler:

  1. Çapraz Bulaşma & Sürüm Kalıntıları (V3 vs V4 İzolasyonu, K=10 vs K=15, imports)
  2. Dosya Kilitlenme & Eşzamanlılık Riskleri (WinError 32, atomic writes, retry locks)
  3. Matematiksel Uç Durumlar (ZeroDivision, NoneType format, NaN sızıntısı)
  4. Ağ & Hata Yönetimi Fail-Safe (Telegram timeout, API kopmaları, 4096 char limit)
================================================================================
"""

import os
import sys
import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

# UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent


class QARedTeamAuditor:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.findings = {
            "cross_contamination": [],
            "file_locking_risks": [],
            "math_edge_cases": [],
            "network_failsafe": []
        }

    def log_finding(self, category: str, severity: str, file_path: str, line_no: int, message: str, code_snippet: str = ""):
        self.findings[category].append({
            "severity": severity,  # HIGH, MEDIUM, LOW, INFO
            "file": file_path,
            "line": line_no,
            "message": message,
            "snippet": code_snippet.strip()
        })

    # ==========================================================================
    # 1. ÇAPRAZ BULAŞMA VE SÜRÜM KALINTILARI DENETİMİ
    # ==========================================================================
    def audit_cross_contamination(self):
        v4_py_files = [
            self.root_dir / "run_paper_trader_v4.py",
            self.root_dir / "models" / "v4_ranking" / "paper_trader_v4.py",
            self.root_dir / "models" / "v4_ranking" / "ranking_pipeline_v4.py",
            self.root_dir / "models" / "v4_ranking" / "drift_monitor_v4.py",
        ]

        # 1.1 V4 dosyalarının V3 modüllerini import etmesi
        for fpath in v4_py_files:
            if not fpath.exists():
                continue
            rel_path = fpath.relative_to(self.root_dir).as_posix()
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                tree = ast.parse(content, filename=str(fpath))
            except Exception as e:
                self.log_finding("cross_contamination", "HIGH", rel_path, 1, f"AST parse hatası: {e}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if "v3_ranking" in mod:
                        # Hangi fonksiyonları çekiyor?
                        imported_names = [n.name for n in node.names]
                        severity = "HIGH" if "ranking_pipeline" in mod or "paper_trader" in mod else "MEDIUM"
                        msg = f"V4 dosyası doğrudan V3 modülü import ediyor: 'from {mod} import {imported_names}'"
                        self.log_finding("cross_contamination", severity, rel_path, node.lineno, msg, f"from {mod} import {', '.join(imported_names)}")

        # 1.2 app.py içinde V3 kalıntısı K=10 veya v3_ranking sızıntısı
        app_file = self.root_dir / "app.py"
        if app_file.exists():
            with open(app_file, "r", encoding="utf-8") as f:
                app_lines = f.readlines()
            for idx, line in enumerate(app_lines, 1):
                # V4 bağlamında hardcoded 0.10 (K=10) ağırlık araması
                if "kasa_buyuklugu * 0.10" in line or "kasa_buyuklugu * 0.1" in line:
                    self.log_finding(
                        "cross_contamination", "HIGH", "app.py", idx,
                        "Hardcoded V3 ağırlığı (%10 / K=10) bulundu. V4 K=15 için ağırlık 1/15 (%6.67) olmalıdır!",
                        line
                    )

        # 1.3 .bat dosyalarında yanlış V3 çağırma kontrolü
        bat_files = list(self.root_dir.glob("*.bat"))
        for b in bat_files:
            rel_path = b.name
            with open(b, "r", encoding="utf-8", errors="ignore") as f:
                bat_text = f.read()
            # TELEGRAM_BOT.bat veya GUNLUK_TARAMA.bat'ta v3_ranking veya yanlış script geçiyor mu?
            if "run_paper_trader.py" in bat_text and not "run_paper_trader_v4.py" in bat_text:
                self.log_finding(
                    "cross_contamination", "HIGH", rel_path, 1,
                    f"{rel_path} dosyası V4 yerine doğrudan eski V3 servisini (run_paper_trader.py) çağırıyor!",
                    bat_text
                )

    # ==========================================================================
    # 2. DOSYA KİLİTLENME VE EŞZAMANLILIK (WINERROR 32 / FILE LOCKING) DENETİMİ
    # ==========================================================================
    def audit_file_locking_and_concurrency(self):
        # 2.1 app.py içindeki dosya okumalarında retry / try-except kontrolü
        app_file = self.root_dir / "app.py"
        if app_file.exists():
            with open(app_file, "r", encoding="utf-8") as f:
                app_content = f.read()
            tree = ast.parse(app_content, filename="app.py")

            # load_latest_ranking ve load_latest_selection fonksiyonlarını bul
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name in ("load_latest_ranking", "load_latest_selection", "load_latest_drift_report"):
                        # Bu fonksiyon içinde time.sleep veya retry loop var mı?
                        func_code = ast.unparse(node)
                        has_retry = ("time.sleep" in func_code) or ("for " in func_code and "range" in func_code)
                        if not has_retry:
                            self.log_finding(
                                "file_locking_risks", "MEDIUM", "app.py", node.lineno,
                                f"'{node.name}' fonksiyonunda dosya kilitlenme (PermissionError / WinError 32) anında retry döngüsü yok. Dosya yazım anında doğrudan None dönüp paneli çökertebilir.",
                                func_code.splitlines()[0]
                            )

        # 2.2 V4 motorunda doğrudan güvensiz 'open(..., w)' veya 'open(..., a)' yazımı
        v4_files = [
            self.root_dir / "models" / "v4_ranking" / "paper_trader_v4.py",
            self.root_dir / "models" / "v4_ranking" / "ranking_pipeline_v4.py",
            self.root_dir / "models" / "v4_ranking" / "drift_monitor_v4.py",
            self.root_dir / "run_paper_trader_v4.py",
        ]

        for fpath in v4_files:
            if not fpath.exists():
                continue
            rel_path = fpath.relative_to(self.root_dir).as_posix()
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for idx, line in enumerate(lines, 1):
                # open(..., "w") arayışı
                if 'open(' in line and ('"w"' in line or "'w'" in line):
                    # .tmp uzantısı kullanılmadan doğrudan asıl dosyaya mı yazılıyor?
                    if ".tmp" not in line and "temp" not in line.lower():
                        self.log_finding(
                            "file_locking_risks", "HIGH", rel_path, idx,
                            "Atomik (.tmp -> os.replace) kullanılmadan doğrudan asıl dosyaya yazma ('w' modu) tespit edildi! Okuma anında WinError 32 ve veri bozulma riski!",
                            line
                        )
                # open(..., "a") arayışı
                elif 'open(' in line and ('"a"' in line or "'a'" in line):
                    # log dosyasına retry olmadan mı ekleniyor?
                    preceding = "".join(lines[max(0, idx-6):idx])
                    if "try:" not in preceding and "attempt" not in preceding:
                        self.log_finding(
                            "file_locking_risks", "LOW", rel_path, idx,
                            "Log dosyasına 'a' (append) modunda retry olmadan yazılıyor. Streamlit aynı anda okursa Windows dosya kilidi hatası oluşabilir.",
                            line
                        )

    # ==========================================================================
    # 3. MATEMATİKSEL UÇ DURUMLAR (ZERODIVISION & NONETYPE FORMAT CRASH)
    # ==========================================================================
    def audit_mathematical_edge_cases(self):
        target_files = [
            self.root_dir / "app.py",
            self.root_dir / "models" / "v4_ranking" / "drift_monitor_v4.py",
            self.root_dir / "models" / "v4_ranking" / "paper_trader_v4.py",
            self.root_dir / "models" / "v4_ranking" / "ranking_pipeline_v4.py",
        ]

        for fpath in target_files:
            if not fpath.exists():
                continue
            rel_path = fpath.relative_to(self.root_dir).as_posix()
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            try:
                tree = ast.parse("".join(lines), filename=rel_path)
            except Exception:
                continue

            for node in ast.walk(tree):
                # 3.1 Sıfıra Bölünme (BinOp Div)
                if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv)):
                    denom = ast.unparse(node.right)
                    line_no = node.lineno
                    line_txt = lines[line_no - 1] if line_no <= len(lines) else ""

                    # Eğer paydada koruma yoksa (max(1, ...), + 1e-9, if ... > 0)
                    unsafe_denoms = [
                        "target_k", "float(target_k)", "alis_fiyati", "high_52",
                        "zirve_52", "sub_u.iloc[lag_idx]", "_xr_ep", "entry_p", "peak_p"
                    ]
                    for un_d in unsafe_denoms:
                        if denom == un_d:
                            # Aynı satırda 'if' koruması var mı?
                            if "if " not in line_txt and "> 0" not in line_txt and "max(" not in line_txt:
                                self.log_finding(
                                    "math_edge_cases", "HIGH", rel_path, line_no,
                                    f"Olası ZeroDivisionError: Payda '{denom}' sıfır veya None geldiğinde çökme riski!",
                                    line_txt
                                )

                # 3.2 F-String Format Çökmesi (NoneType / NaN formatlama)
                if isinstance(node, ast.JoinedStr):
                    # F-string içindeki formatlanan değerleri denetle
                    for val in node.values:
                        if isinstance(val, ast.FormattedValue) and val.format_spec:
                            spec = ast.unparse(val.format_spec)
                            expr = ast.unparse(val.value)
                            line_no = val.lineno
                            line_txt = lines[line_no - 1] if line_no <= len(lines) else ""

                            if any(fmt in spec for fmt in [".2f", ".1f", "+.2f", ".4f", "+,.2f"]):
                                # Eğer değer doğrudan None dönebilecek bir fonksiyonsa ve 'or 0' yoksa
                                if (".get(" in expr or expr in ["_xr_kz", "_xr_karne_skor", "alfa_period"]) and " or " not in expr and " if " not in expr:
                                    self.log_finding(
                                        "math_edge_cases", "LOW", rel_path, line_no,
                                        f"Riskli f-string float formatlaması: '{expr}' None gelirse TypeError fırlatır!",
                                        line_txt
                                    )

    # ==========================================================================
    # 4. AĞ VE HATA YÖNETİMİ (FAIL-SAFE) DENETİMİ
    # ==========================================================================
    def audit_network_failsafe(self):
        bot_file = self.root_dir / "bot" / "telegram_bot.py"
        if bot_file.exists():
            with open(bot_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Timeout kontrolü
            if "timeout=" not in content:
                self.log_finding(
                    "network_failsafe", "HIGH", "bot/telegram_bot.py", 1,
                    "Telegram requests.post çağrısında timeout parametresi yok! İnternet donduğunda servis sonsuza kadar kilitlenebilir.",
                    ""
                )

            # 4096 Karakter sınırı kontrolü
            if "4096" not in content and "4000" not in content and "len(metin)" not in content:
                self.log_finding(
                    "network_failsafe", "MEDIUM", "bot/telegram_bot.py", 34,
                    "Telegram 4096 karakter sınır kontrolü ve mesaj bölme (chunking) mekanizması eksik. Çok uzun raporlarda HTTP 400 döner.",
                    "def mesaj_gonder(metin: str, parse_mode: str = 'HTML') -> bool:"
                )

        # Çağıran yerlerde try-except koruması var mı?
        v4_trader_file = self.root_dir / "models" / "v4_ranking" / "paper_trader_v4.py"
        if v4_trader_file.exists():
            with open(v4_trader_file, "r", encoding="utf-8") as f:
                content = f.read()
            if "mesaj_gonder" in content:
                try:
                    tree = ast.parse(content, filename=str(v4_trader_file))
                    is_inside_try = False
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Try):
                            for sub in ast.walk(node):
                                if isinstance(sub, ast.Call):
                                    func_name = getattr(sub.func, "id", "") or getattr(sub.func, "attr", "")
                                    if func_name == "mesaj_gonder":
                                        is_inside_try = True
                                        break
                    if not is_inside_try:
                        self.log_finding(
                            "network_failsafe", "MEDIUM", "models/v4_ranking/paper_trader_v4.py", 355,
                            "Telegram mesaj gönderimi try-except bloğu içine sarılmamış olabilir.",
                            ""
                        )
                except Exception:
                    pass

    def run_all(self):
        print("=" * 80)
        print("🔍 KIDEMLİ QA & RED TEAM OTONOM SİSTEM AUDIT BAŞLATILIYOR...")
        print("=" * 80)

        self.audit_cross_contamination()
        self.audit_file_locking_and_concurrency()
        self.audit_mathematical_edge_cases()
        self.audit_network_failsafe()

        # Raporlama
        total_findings = sum(len(v) for v in self.findings.values())
        print(f"\nAudit Tamamlandı! Toplam {total_findings} Potansiyel Bulgulama Tespit Edildi.\n")

        categories = [
            ("cross_contamination", "1. Çapraz Bulaşma & Sürüm Kalıntıları (V3 vs V4)"),
            ("file_locking_risks", "2. Dosya Kilitlenme & Eşzamanlılık Riskleri (WinError 32)"),
            ("math_edge_cases", "3. Matematiksel Uç Durumlar (ZeroDivision & NoneType)"),
            ("network_failsafe", "4. Ağ & Hata Yönetimi Fail-Safe (Telegram API)")
        ]

        for cat_key, cat_title in categories:
            items = self.findings[cat_key]
            print("-" * 80)
            print(f"📌 {cat_title} ({len(items)} Adet)")
            print("-" * 80)
            if not items:
                print("  ✅ [TEMİZ] Hiçbir güvenlik zafiyeti veya hata tespit edilmedi.")
            else:
                for idx, it in enumerate(items, 1):
                    sev_icon = "🔴 [HIGH]" if it["severity"] == "HIGH" else ("🟡 [MEDIUM]" if it["severity"] == "MEDIUM" else "🔵 [LOW]")
                    print(f"  {idx}. {sev_icon} {it['file']}:{it['line']}")
                    print(f"     Açıklama: {it['message']}")
                    if it["snippet"]:
                        print(f"     Kod: {it['snippet']}")
            print()

        return self.findings


if __name__ == "__main__":
    auditor = QARedTeamAuditor(ROOT_DIR)
    auditor.run_all()
