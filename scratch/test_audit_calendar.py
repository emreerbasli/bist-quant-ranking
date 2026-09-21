import sys, os
sys.path.insert(0, os.path.abspath("."))
import config as cfg
from datetime import datetime

test_dates = [
    # Geçmiş 2026 bayramları
    ("2026-03-19", "Ramazan Arife", True, True),     # is_gunu: True (yarım), yarim: True
    ("2026-03-20", "Ramazan 1. Gün", False, False),  # is_gunu: False, yarim: False
    ("2026-05-26", "Kurban Arife", True, True),      # is_gunu: True (yarım), yarim: True
    ("2026-05-27", "Kurban 1. Gün", False, False),   # is_gunu: False, yarim: False
    ("2026-05-28", "Kurban 2. Gün", False, False),   # is_gunu: False, yarim: False
    ("2026-05-29", "Kurban 3. Gün", False, False),   # is_gunu: False, yarim: False
    # Gelecek 2026 tatilleri (17 Eylül sonrası)
    ("2026-10-28", "Cumhuriyet Arife", True, True),  # is_gunu: True (yarım), yarim: True
    ("2026-10-29", "Cumhuriyet Bayramı", False, False), # is_gunu: False, yarim: False
    # Normal işlem günleri ve hafta sonları
    ("2026-09-17", "Bugün (Perşembe)", True, False),
    ("2026-09-19", "Cumartesi", False, False),
    ("2026-09-20", "Pazar", False, False),
]

all_passed = True
for dt_str, desc, exp_is_gunu, exp_yarim in test_dates:
    dt = datetime.strptime(dt_str, "%Y-%m-%d")
    is_gunu = cfg.bist_is_gunu_mu(dt)
    yarim = cfg.bist_yarim_gun_mu(dt)
    match = (is_gunu == exp_is_gunu) and (yarim == exp_yarim)
    status = "OK" if match else "FAIL"
    if not match:
        all_passed = False
    print(f"[{status}] {dt_str} ({desc}): is_gunu={is_gunu} (exp {exp_is_gunu}), yarim={yarim} (exp {exp_yarim})")

print(f"\nSonuç: {'TÜM TARİHLER BAŞARILI' if all_passed else 'UYUMSUZLUK VAR'}")
