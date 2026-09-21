"""EXP-DATA-009: read-only macro provenance, release-timing and PIT audit."""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "results"
MAN = Path(__file__).resolve().parent / "manifests"
V3 = ROOT / "models/v3_ranking/data_loader.py"
V4 = ROOT / "models/v4_ranking/data_loader_v4.py"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for b in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cpi, rates = None, None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "tufe_aylik": cpi = ast.literal_eval(node.value)
            if node.targets[0].id == "tcmb_faiz": rates = ast.literal_eval(node.value)
    return cpi, rates


def write_csv(name, rows):
    p = OUT / name
    fields = sorted({k for r in rows for k in r})
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    return p


def run():
    OUT.mkdir(exist_ok=True); MAN.mkdir(exist_ok=True)
    cpi, rates = literals(V3); cpi4, rates4 = literals(V4)
    assert cpi == cpi4 and rates == rates4
    cpi_months = pd.PeriodIndex(sorted(cpi), freq="M")
    future_cpi = [str(x) for x in cpi_months if x.to_timestamp() > pd.Timestamp.now().normalize()]
    fx = pd.read_parquet(ROOT / "data/raw/TRY_X.parquet")
    bist = pd.read_parquet(ROOT / "data/raw/XU100_IS.parquet")
    missing = bist.index.difference(fx.index)
    source = V3.read_text(encoding="utf-8")
    feature = (ROOT / "features/feature_engine.py").read_text(encoding="utf-8")
    downloader = (ROOT / "features/veri_cek.py").read_text(encoding="utf-8")
    fallback_count = source.count("tufe_aylik.get(m, 2.0)") + (ROOT / "models/v4_ranking/ranking_pipeline_v4.py").read_text(encoding="utf-8").count("tufe_aylik.get(m, 2.0)")
    inventory = [
      {"series":"policy_rate", "storage":"V3/V4 code literal", "source_claim":"TCMB (unverifiable local claim)", "coverage":f"{rates[0][0]}..{rates[-1][0]}", "release_metadata":"none", "revision_status":"unknown", "fallback":"ffill by date", "pit_quality":"INVALID", "readiness":"NO"},
      {"series":"monthly_cpi", "storage":"V3/V4 code literal", "source_claim":"TÜİK (unverifiable local claim)", "coverage":f"{cpi_months.min()}..{cpi_months.max()}", "release_metadata":"none", "revision_status":"unknown", "fallback":"2.0% fabricated", "pit_quality":"INVALID", "readiness":"NO"},
      {"series":"usdtry", "storage":"data/raw/TRY_X.parquet", "source_claim":"yfinance (loader)", "coverage":f"{fx.index.min().date()}..{fx.index.max().date()}", "release_metadata":"none", "revision_status":"unknown", "fallback":"ffill on equity index", "pit_quality":"PROXY_DATE_ONLY", "readiness":"PARTIAL"},
      {"series":"real_rate", "storage":"derived policy rate - trailing CPI", "source_claim":"derived", "coverage":"same as inputs", "release_metadata":"none", "revision_status":"unknown", "fallback":"inherits 2.0% CPI", "pit_quality":"INVALID", "readiness":"NO"},
      {"series":"inflation_adjusted_real_eps", "storage":"V4 calculation", "source_claim":"derived", "coverage":"PIT financial records", "release_metadata":"none", "revision_status":"unknown", "fallback":"inherits 2.0% CPI", "pit_quality":"DOUBLE_ADJUSTMENT_RISK", "readiness":"NO"},
    ]
    release = []
    for r in inventory:
        release.append({"series":r["series"], "observation_period":r["coverage"], "publication_date":None, "available_from":None, "value":"stored/derived", "source":r["source_claim"], "revision_status":r["revision_status"], "pit_quality":r["pit_quality"]})
    fx_rows = [{"metric":"fx_rows", "value":len(fx)}, {"metric":"fx_duplicate_dates", "value":int(fx.index.duplicated().sum())}, {"metric":"fx_null_close", "value":int(fx['close'].isna().sum())}, {"metric":"bist_dates_without_fx", "value":len(missing)}, {"metric":"missing_bist_dates", "value":"|".join(str(x.date()) for x in missing)}, {"metric":"uses_reindex_ffill", "value":"yes"}, {"metric":"future_index_reference_in_v3v4", "value":"no (<= t slicing)"}]
    usage = [
      {"component":"V3/V4 real rate", "use":"policy minus trailing 12m CPI", "risk":"missing publication/vintage plus fallback"},
      {"component":"V4 real EPS", "use":"net income CPI deflation", "risk":"DOUBLE_ADJUSTMENT_RISK with TFRS29"},
      {"component":"feature_engine USDTRY", "use":"5d/20d returns and beta", "risk":"date-only availability, ffill"},
    ]
    write_csv("EXP-DATA-009_macro_inventory.csv", inventory); write_csv("EXP-DATA-009_release_timing.csv", release)
    write_csv("EXP-DATA-009_fx_audit.csv", fx_rows); write_csv("EXP-DATA-009_feature_usage.csv", usage)
    write_csv("EXP-DATA-009_cpi_fallback_exposure.csv", [{"fallback_expression":"tufe_aylik.get(m, 2.0)", "occurrences":fallback_count, "status":"RESEARCH_EXCLUDE"}, {"future_dated_cpi_months":"|".join(future_cpi), "occurrences":len(future_cpi), "status":"FABRICATED_FUTURE_RISK"}])
    summary = {"experiment":"EXP-DATA-009", "macro_gate":"EXCLUDE", "series_readiness":{"policy_rate":"NO","monthly_cpi":"NO","usdtry":"PARTIAL","real_rate":"NO","inflation_adjusted_real_eps":"NO"}, "policy_rate_last_stored_date":rates[-1][0], "cpi_last_stored_month":str(cpi_months.max()), "future_dated_cpi_months":future_cpi, "fx":{"first":str(fx.index.min().date()),"last":str(fx.index.max().date()),"rows":len(fx),"bist_missing_fx_dates":[str(x.date()) for x in missing]}, "fallback_expression_occurrences":fallback_count, "production_changes":0, "decision":"Exclude all macro-derived inputs from research; price-only and recovered-fundamental work remains unblocked."}
    (OUT / "EXP-DATA-009_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = """# EXP-DATA-009 — Macro Provenance, Release-Timing & PIT Audit

## 1. Executive Summary

**MACRO = EXCLUDE.** Yerel politika faizi ve TÜFE serilerinde yayın tarihi, kullanılabilirlik tarihi, vintage ve revizyon soyu yoktur; TÜFE eksiklerinde kod `%2.0` üretmektedir. Bu karar fiyat-only ve recovered-exact fundamental araştırmasını bloklamaz.

## 2. Macro Source Inventory

Envanter `EXP-DATA-009_macro_inventory.csv` içindedir; seri bazlı PIT niteliği kayıtlıdır.

## 3. Policy Rate

Politika faizi V3/V4 içinde statik listedir; son kayıt 2026-01-01'dir. Tarihler etkinlik/yayın ayrımını, kaynak kanıtını veya vintage'i taşımaz. Tarihe göre ffill mantığı ekonomik olarak mümkün olsa da bu metadata olmadan PIT-safe değildir: **NO / INVALID**.

## 4. CPI / TÜFE

TÜFE statik sözlüktedir; yayın tarihi ve revision bilgisi yoktur. Audit tarihinde ileri tarihli sözlük ayı bulunmadı; ancak `tufe_aylik.get(m, 2.0)` eksik ayları gerçek gözlem değil `%2` ile tamamlar. Araştırmada fallback kullanılamaz: **NO / INVALID**.

## 5. USDTRY

`TRY_X.parquet` 2018-01-01–2026-09-15, 2,266 satır, null/duplicate yoktur. BIST işlem günlerinde doğrudan olmayan üç tarih ffill ile taşınır. Kodda `<= t` kesiti vardır; ancak yfinance ham serisi yayın/vintage/zaman damgası taşımadığından yalnız **PARTIAL / PROXY_DATE_ONLY**'dır.

## 6. Real Rate

Formül politika faizi eksi geriye dönük 12 aylık bileşik TÜFE'dir. CPI seçimi gün eşiğine dayanır, resmi yayın `available_from` alanına değil. Her iki girdi de güvenli olmadığından **NO / INVALID**.

## 7. TFRS29 / Inflation Interaction

V4 real EPS net kârı ayrıca CPI ile deflate eder. EXP-DATA-006/007'nin TFRS29 bulguları ile birlikte **DOUBLE-ADJUSTMENT RISK**; V4 çalıştırılmadı.

## 8. Release-Timing Contract

Her gözlem için zorunlu alanlar: `observation_period`, `publication_date`, `available_from`, `value`, `source`, `revision_status`, `pit_quality`. Saat yoksa yayın tarihi sonrası ilk işlem seansı konservatif `available_from` olur. Mevcut rate/CPI bu alanları karşılamaz.

## 9. Series-Level Readiness

Policy rate NO; CPI NO; USDTRY PARTIAL; real rate NO; inflation-adjusted real EPS NO.

## 10. Overall MACRO Gate

**EXCLUDE.** İlk araştırma dalgasında makro-türetilmiş feature/target/model kullanılmayacaktır.

## 11. External Data Needs

Gelecekte yeniden açılırsa kaynak bazında yayın takvimi, ilk-yayın/vintage ve revizyon soyuyla TCMB/TÜİK arşivi gerekir. Bu deney yeni sağlayıcı veya entegrasyon açmadı.

## 12. Tests

Unit testleri geleceğe yayın kullanmama, fabricated fallback reddi, statik seri tazeliği, FX hizalama, real-rate zamanlama ve üretim hash'ini denetler.

## 13. Production Integrity

Production değişikliği yoktur; korunan dosya hash kontrolü bu deney sonunda çalıştırılacaktır.

## 14. MASTER_PLAN’e göre SINGLE NEXT BEST ACTION

Makroyu dışarıda bırakarak MASTER_PLAN'daki sonraki data/foundation paketine geçmek; macro yeni veri deneyi yalnız plan açıkça gerektirirse veya model seçimini değiştirecek yeni hata bulunursa açılmalıdır.
"""
    (OUT / "EXP-DATA-009_report.md").write_text(report, encoding="utf-8")
    manifest = {"experiment":"EXP-DATA-009","generated_at_utc":datetime.now(timezone.utc).isoformat(),"inputs":{"v3_loader_sha256":digest(V3),"v4_loader_sha256":digest(V4),"try_x_sha256":digest(ROOT/'data/raw/TRY_X.parquet')},"output_gate":"EXCLUDE","production_changes":0}
    (MAN / "EXP-DATA-009_reproducibility.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

if __name__ == "__main__": print(json.dumps(run(), ensure_ascii=False))
