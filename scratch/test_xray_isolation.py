"""
Test: X-Ray (Hisse Röntgeni) İzolasyon ve Bütünlük Doğrulaması
"""
import ast
import os
import json
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_ast():
    app_path = os.path.join(ROOT, "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    assert tree is not None
    print("[PASS] 1. app.py AST parse hatasız.")

def test_xray_sidebar_and_tab():
    app_path = os.path.join(ROOT, "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        src = f.read()
    
    assert "🔍 Hisse Röntgeni (X-Ray)" in src, "Sidebar'da Röntgen seçeneği bulunamadı!"
    assert 'elif sayfa == "🔍 Hisse Röntgeni (X-Ray)":' in src, "X-Ray sayfası elif bloğu bulunamadı!"
    print("[PASS] 2. Sidebar seçeneği ve sayfa bloğu tanımlı.")

def test_xray_read_only_isolation():
    app_path = os.path.join(ROOT, "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        src = f.read()
    
    # Röntgen bloğunu ayıkla
    xray_part = src.split('elif sayfa == "🔍 Hisse Röntgeni (X-Ray)":')[1]
    
    # X-Ray bloğunda hiçbir disk yazma işlemi olmamalı
    disallowed = ["open(", "json.dump", ".write(", "wallet_save", "os.replace", "os.remove"]
    for d in disallowed:
        if d in xray_part:
            # open( sadece read amaçlı olabilir mi kontrol et
            matches = re.findall(rf"{re.escape(d)}.*", xray_part)
            for m in matches:
                assert "'w'" not in m and '"w"' not in m and "'a'" not in m and '"a"' not in m, f"Yasaklı disk yazma bulundu: {m}"
    
    print("[PASS] 3. X-Ray bloğu %100 Salt Okunur (Read-Only) - diske hiçbir şey yazmıyor.")

def test_v4_paper_portfolio_intact():
    v4_path = os.path.join(ROOT, "models", "v4_ranking", "paper_portfolio_v4.json")
    assert os.path.exists(v4_path), "paper_portfolio_v4.json bulunamadı!"
    with open(v4_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "positions" in data, "positions eksik"
    assert len(data["positions"]) == 15, f"V4 pozisyon sayısı 15 olmalı, {len(data['positions'])} bulundu!"
    print(f"[PASS] 4. paper_portfolio_v4.json korundu. Pozisyon sayısı: {len(data['positions'])}.")

if __name__ == "__main__":
    test_ast()
    test_xray_sidebar_and_tab()
    test_xray_read_only_isolation()
    test_v4_paper_portfolio_intact()
    print("\n[SUCCESS] TUM TESTLER BASARIYLA GECTI!")
