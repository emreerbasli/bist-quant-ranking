"""
scratch/faz1_ic_tarama.py
=========================
FAZ 1: BİREYSEL BİLGİ KATSAYISI (SPEARMAN RANK IC) TARAMASI
------------------------------------------------------------
8 Aday Feature (+ z_borc_oz karşılaştırması):
  1. eps_accel         (Kâr büyüme ivmesi)
  2. accruals_ratio    (Tahakkuk anomalisi - Sloan 1996)
  3. reel_eps_growth   (Enflasyondan arındırılmış kâr büyümesi)
  4. satislar_growth   (Yıllık ciro büyümesi)
  5. op_marji_trend    (Faaliyet kâr marjı trendi)
  6. ihracat_kalkani   (İhracat oranı x USD momentum)
  7. reversal_penalty  (Kısa vadeli 5g/10g aşırı alım)
  8. usd_vol_rejim     (Net FX pozisyonu / İhracat x USD volatilite)
  +  z_borc_oz         (Özkaynak bazlı net borç)

Pencere: Sadece Eğitim Seti (2019-09 -> 2024-12)
Kilit kutu (2025-06 -> 2026-09) KESİNLİKLE KULLANILMAZ.
3-Kategori Karar Kuralları:
  ❌ Red:     |mean IC| < 0.02 VEYA beklenen işaretin tersi
  ⚠️ Sınırda: 0.02 <= |mean IC| < 0.03 VEYA (|mean IC| >= 0.02 VE IC-IR < 0.5)
              -> Dönem A (2019-2022) / Dönem B (2023-2024) Rejim Testi
  ✅ Kabul:   |mean IC| >= 0.03 VE IC-IR >= 0.5 (doğru işaret)
"""

import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, t as student_t

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config as cfg
from models.v3_ranking.data_loader import yukle_veriler


def get_yoy_and_prev_records(
    gecerli_recs: List[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    PIT kayıtlarından sırasıyla:
      - curr: En güncel çeyrek
      - yoy:  1 yıl önceki aynı çeyrek (t - 4Q)
      - prev: 1 önceki çeyrek (t - 1Q)
      - prev_yoy: 1 önceki çeyreğin 1 yıl öncesi (t - 5Q)
    döner.
    """
    if not gecerli_recs:
        return None, None, None, None

    curr = gecerli_recs[-1]
    curr_q_str = curr.get("ceyrek", "")
    if len(curr_q_str) < 6:
        # Format uymuyorsa index bazlı fallback
        yoy = gecerli_recs[-5] if len(gecerli_recs) >= 5 else None
        prev = gecerli_recs[-2] if len(gecerli_recs) >= 2 else None
        prev_yoy = gecerli_recs[-6] if len(gecerli_recs) >= 6 else None
        return curr, yoy, prev, prev_yoy

    try:
        curr_year = int(curr_q_str[:4])
        curr_q = int(curr_q_str[-1])
    except Exception:
        yoy = gecerli_recs[-5] if len(gecerli_recs) >= 5 else None
        prev = gecerli_recs[-2] if len(gecerli_recs) >= 2 else None
        prev_yoy = gecerli_recs[-6] if len(gecerli_recs) >= 6 else None
        return curr, yoy, prev, prev_yoy

    target_yoy = f"{curr_year - 1}Q{curr_q}"
    if curr_q > 1:
        target_prev = f"{curr_year}Q{curr_q - 1}"
        target_prev_yoy = f"{curr_year - 1}Q{curr_q - 1}"
    else:
        target_prev = f"{curr_year - 1}Q4"
        target_prev_yoy = f"{curr_year - 2}Q4"

    q_map = {r.get("ceyrek"): r for r in gecerli_recs}
    yoy = q_map.get(target_yoy)
    prev = q_map.get(target_prev)
    prev_yoy = q_map.get(target_prev_yoy)

    # Fallback if quarter name missing
    if yoy is None and len(gecerli_recs) >= 5:
        yoy = gecerli_recs[-5]
    if prev is None and len(gecerli_recs) >= 2:
        prev = gecerli_recs[-2]
    if prev_yoy is None and len(gecerli_recs) >= 6:
        prev_yoy = gecerli_recs[-6]

    return curr, yoy, prev, prev_yoy


def hesapla_yillik_tufe(t: pd.Timestamp, tufe_aylik: Dict[str, float]) -> float:
    """t tarihindeki son açıklanan 12 aylık kümülatif TÜFE enflasyon oranını döner (ör: 0.65)."""
    son_ay_dt = (t - pd.DateOffset(months=2 if t.day < 4 else 1)).replace(day=1)
    aylar = pd.date_range(end=son_ay_dt, periods=12, freq="MS").strftime("%Y-%m").tolist()
    factors = [1.0 + tufe_aylik.get(m, 2.0) / 100.0 for m in aylar]
    return float(np.prod(factors) - 1.0)


def extract_candidate_features(
    t: pd.Timestamp,
    sembol: str,
    fiyat_seri: pd.Series,
    seri_usdtry: pd.Series,
    pit_recs: List[Dict[str, Any]],
    tufe_aylik: Dict[str, float]
) -> Dict[str, float]:
    """
    Belirtilen tarih ve hisse için 8 aday feature (+ z_borc_oz) değerini hesaplar.
    """
    res = {}
    gecerli = [r for r in pit_recs if r["gecerlilik_tarihi"] <= t]
    if not gecerli:
        return res

    curr, yoy, prev, prev_yoy = get_yoy_and_prev_records(gecerli)
    if not curr:
        return res

    is_bank = bool(curr.get("is_bank", False))
    net_kar_c = curr.get("net_kar") or 0.0
    aktif_c = curr.get("toplam_aktif") or 0.0
    cfo_c = curr.get("cfo") or 0.0
    satis_c = curr.get("satislar") or 0.0
    op_c = curr.get("op_gelir") or 0.0
    ozk_c = curr.get("ozkaynaklar") or 0.0
    net_borc_c = curr.get("net_borc") or 0.0
    ihracat_c = curr.get("ihracat_orani")
    net_fx_c = curr.get("net_fx") or 0.0
    pd_c = curr.get("piyasa_degeri") or 0.0

    # Fiyat / Getiri değişkenleri
    p_past = fiyat_seri[fiyat_seri.index <= t]
    p_last = p_past.iloc[-1] if len(p_past) > 0 else 0.0

    # 1. eps_accel (Kâr büyüme ivmesi)
    # Asset-scaled standard formulation:
    if yoy and prev and prev_yoy and aktif_c > 0:
        net_kar_y = yoy.get("net_kar") or 0.0
        net_kar_p = prev.get("net_kar") or 0.0
        net_kar_py = prev_yoy.get("net_kar") or 0.0
        aktif_p = prev.get("toplam_aktif") or aktif_c

        d_curr = (net_kar_c - net_kar_y) / max(1e6, abs(aktif_c))
        d_prev = (net_kar_p - net_kar_py) / max(1e6, abs(aktif_p))
        res["eps_accel"] = float(np.clip(d_curr - d_prev, -2.0, 2.0))
    else:
        res["eps_accel"] = np.nan

    # 2. accruals_ratio (Sloan 1996: (Net Kar - CFO) / Toplam Aktif)
    # Bankalarda CFO kavramı farklı olduğu için NaN bırakılır
    if not is_bank and aktif_c > 0 and pd.notna(cfo_c):
        res["accruals_ratio"] = float(np.clip((net_kar_c - cfo_c) / max(1e6, abs(aktif_c)), -1.0, 1.0))
    else:
        res["accruals_ratio"] = np.nan

    # 3. reel_eps_growth (Enflasyondan arındırılmış kâr büyümesi)
    if yoy and aktif_c > 0:
        pi_12m = hesapla_yillik_tufe(t, tufe_aylik)
        net_kar_y = yoy.get("net_kar") or 0.0
        # Reel cari net kâr (t-4Q fiyatlarına indirgenmiş)
        net_kar_reel = net_kar_c / (1.0 + max(-0.5, pi_12m))
        res["reel_eps_growth"] = float(np.clip((net_kar_reel - net_kar_y) / max(1e6, abs(aktif_c)), -2.0, 2.0))
    else:
        res["reel_eps_growth"] = np.nan

    # 4. satislar_growth (Yıllık Satış / Ciro Büyümesi)
    if yoy and not is_bank:
        satis_y = yoy.get("satislar") or 0.0
        if satis_y > 1e5:
            res["satislar_growth"] = float(np.clip((satis_c - satis_y) / satis_y, -0.9, 5.0))
        else:
            res["satislar_growth"] = np.nan
    else:
        res["satislar_growth"] = np.nan

    # 5. op_marji_trend (Faaliyet Marjı Trendi: Marj_t - Marj_t-4Q)
    if yoy and not is_bank:
        satis_y = yoy.get("satislar") or 0.0
        op_y = yoy.get("op_gelir") or 0.0
        if satis_c > 1e5 and satis_y > 1e5:
            marj_c = op_c / satis_c
            marj_y = op_y / satis_y
            res["op_marji_trend"] = float(np.clip(marj_c - marj_y, -0.5, 0.5))
        else:
            res["op_marji_trend"] = np.nan
    else:
        res["op_marji_trend"] = np.nan

    # USD/TRY metrikleri
    u_past = seri_usdtry[seri_usdtry.index <= t]
    usd_mom_60 = 0.0
    usd_vol_60 = 0.0
    if len(u_past) >= 61:
        usd_mom_60 = float((u_past.iloc[-1] - u_past.iloc[-61]) / u_past.iloc[-61])
        u_ret = u_past.pct_change().iloc[-60:].dropna()
        usd_vol_60 = float(u_ret.std() * np.sqrt(252))

    # 6. ihracat_kalkani (İhracat Oranı x max(0, USD Momentum))
    if pd.notna(ihracat_c) and ihracat_c is not None:
        ihr_val = float(ihracat_c)
        if ihr_val > 1.0:
            ihr_val /= 100.0  # Yüzde 50 girilmişse 0.5 yap
        res["ihracat_kalkani"] = float(ihr_val * max(0.0, usd_mom_60))
    else:
        res["ihracat_kalkani"] = 0.0 if not is_bank else np.nan

    # 7. reversal_penalty (Kısa Vadeli 5 Günlük Fiyat Primi / Reversal)
    # Beklenen yön: Negatif (Son 5 günde çok koşan gelecek 60g'de düzeltme yer)
    if len(p_past) >= 6 and p_past.iloc[-6] > 0:
        res["reversal_penalty"] = float((p_past.iloc[-1] - p_past.iloc[-6]) / p_past.iloc[-6])
    else:
        res["reversal_penalty"] = np.nan

    # 8. usd_vol_rejim (Net FX Exposure x USD Volatilite)
    if pd_c > 1e6 and pd.notna(net_fx_c):
        fx_ratio = float(np.clip(net_fx_c / pd_c, -1.0, 1.0))
        res["usd_vol_rejim"] = float(fx_ratio * usd_vol_60)
    elif pd.notna(ihracat_c):
        ihr_val = float(ihracat_c)
        if ihr_val > 1.0:
            ihr_val /= 100.0
        res["usd_vol_rejim"] = float(ihr_val * usd_vol_60)
    else:
        res["usd_vol_rejim"] = np.nan

    # Bonus Faz 6: z_borc_oz (Özkaynak Bazlı Net Borç Ters Çevrilmiş: -Net Borç / Özkaynak)
    if not is_bank and ozk_c > 1e5:
        res["z_borc_oz"] = float(np.clip(-net_borc_c / ozk_c, -5.0, 5.0))
    else:
        res["z_borc_oz"] = np.nan

    return res


def run_faz1_ic_screening():
    """
    Faz 1 IC taramasını 2019-09 -> 2024-12 eğitim kümesinde icra eder.
    """
    print("=" * 105)
    print("FAZ 1: BİREYSEL SPEARMAN RANK IC TARAMASI (2019-09 -> 2024-12)")
    print("3-Kategori Eşik Sistemi: Kabul (|IC|>=0.03 & IR>=0.5) | Sınırda (Rejim Testi) | Red (<0.02)")
    print("=" * 105)

    fiyat_dict, seri_xu100, seri_usdtry, pit_bellek, cache_bellek, tufe_aylik = yukle_veriler()

    # Eğitim penceresi rebalance tarihleri (3 aylık periyotlar)
    tarihler = pd.date_range("2019-09-01", "2024-12-01", freq="3MS")
    hisseler = sorted(fiyat_dict.keys())

    candidate_names = [
        "eps_accel",
        "accruals_ratio",
        "reel_eps_growth",
        "satislar_growth",
        "op_marji_trend",
        "ihracat_kalkani",
        "reversal_penalty",
        "usd_vol_rejim",
        "z_borc_oz",
    ]

    expected_signs = {
        "eps_accel": +1,
        "accruals_ratio": -1,
        "reel_eps_growth": +1,
        "satislar_growth": +1,
        "op_marji_trend": +1,
        "ihracat_kalkani": +1,
        "reversal_penalty": -1,
        "usd_vol_rejim": 0,  # Rejim bağımlı
        "z_borc_oz": +1,
    }

    # Çeyrek bazlı IC kayıtları
    ic_records = []

    for i in range(len(tarihler) - 1):
        t0, t1 = tarihler[i], tarihler[i + 1]

        # 60 günlük forward return hesapla
        rets = {}
        for s, seri in fiyat_dict.items():
            p_slice = seri[(seri.index >= t0) & (seri.index <= t1)]
            if len(p_slice) >= 3 and p_slice.iloc[0] > 0:
                rets[s] = float(np.clip((p_slice.iloc[-1] - p_slice.iloc[0]) / p_slice.iloc[0], -0.9, 8.0))

        mevcut_hisseler = [s for s in hisseler if s in rets]
        if len(mevcut_hisseler) < 30:
            continue

        # Dönem A (2019-2022 Negatif Reel Faiz) vs Dönem B (2023-2024 Pozitif Reel Faiz)
        donem_kodu = "Donem_A" if t0 < pd.Timestamp("2023-01-01") else "Donem_B"

        rows = []
        for s in mevcut_hisseler:
            row = {"sembol": s, "fwd_ret": rets[s]}
            feats = extract_candidate_features(
                t0, s, fiyat_dict[s], seri_usdtry, pit_bellek.get(s, []), tufe_aylik
            )
            row.update(feats)
            rows.append(row)

        df_t = pd.DataFrame(rows)

        ic_entry = {"t": t0, "donem": donem_kodu, "n_hisse": len(df_t)}
        for c in candidate_names:
            sub = df_t[[c, "fwd_ret"]].dropna()
            if len(sub) >= 15 and sub[c].std() > 1e-7:
                corr, _ = spearmanr(sub[c], sub["fwd_ret"])
                ic_entry[c] = corr
            else:
                ic_entry[c] = np.nan

        ic_records.append(ic_entry)

    df_ic = pd.DataFrame(ic_records)
    print(f"\nToplam Değerlendirilen Çeyrek Kesiti: {len(df_ic)} periyot (Dönem A: {len(df_ic[df_ic['donem'] == 'Donem_A'])}, Dönem B: {len(df_ic[df_ic['donem'] == 'Donem_B'])})")

    # Sonuçların Hesaplanması
    results = []
    for c in candidate_names:
        seri_ic = df_ic[c].dropna()
        n_obs = len(seri_ic)
        if n_obs < 8:
            continue

        mean_ic = seri_ic.mean()
        std_ic = seri_ic.std(ddof=1)
        ic_ir = mean_ic / std_ic if std_ic > 1e-7 else 0.0

        # t-statistic ve p-değeri
        t_stat = ic_ir * np.sqrt(n_obs)
        p_val = 2.0 * (1.0 - student_t.cdf(abs(t_stat), df=n_obs - 1))

        # Rejim A ve Rejim B Alt Kümeleri
        seri_a = df_ic[df_ic["donem"] == "Donem_A"][c].dropna()
        mean_a = seri_a.mean() if len(seri_a) > 0 else np.nan
        std_a = seri_a.std(ddof=1) if len(seri_a) > 1 else np.nan
        ir_a = mean_a / std_a if std_a and std_a > 1e-7 else np.nan

        seri_b = df_ic[df_ic["donem"] == "Donem_B"][c].dropna()
        mean_b = seri_b.mean() if len(seri_b) > 0 else np.nan
        std_b = seri_b.std(ddof=1) if len(seri_b) > 1 else np.nan
        ir_b = mean_b / std_b if std_b and std_b > 1e-7 else np.nan

        exp_sign = expected_signs.get(c, 0)
        # İşaret Tutarlılığı Kontrolü:
        sign_ok = True
        if exp_sign > 0 and mean_ic < 0:
            sign_ok = False
        elif exp_sign < 0 and mean_ic > 0:
            sign_ok = False

        # 3-Kategori Karar Mantığı:
        abs_ic = abs(mean_ic)
        karar = "❌ RED"
        gerekce = ""

        if not sign_ok and exp_sign != 0:
            karar = "❌ RED (TERS İŞARET)"
            gerekce = f"Beklenen işaret {exp_sign:+} iken gerçekleşen {np.sign(mean_ic):+}. Overfitting / gürültü kanıtı."
        elif abs_ic < 0.02:
            karar = "❌ RED (|IC| < 0.02)"
            gerekce = f"Ortalama |IC| ({abs_ic:.4f}) < 0.02 eşiği. Sinyal gücü yetersiz."
        elif abs_ic >= 0.03 and ic_ir >= 0.5 and sign_ok:
            karar = "✅ KABUL"
            gerekce = f"Güçlü ve istikrarlı sinyal (|IC|={abs_ic:.4f} >= 0.03, IR={ic_ir:.2f} >= 0.5)."
        else:
            # Sınırda Durumu (0.02 <= |IC| < 0.03 VEYA IR < 0.5)
            # Rejim testi: Dönem A veya Dönem B'den en az birinde |IC| >= 0.03 VE IR >= 0.5 var mı?
            pass_a = pd.notna(mean_a) and pd.notna(ir_a) and (abs(mean_a) >= 0.03) and (abs(ir_a) >= 0.5)
            pass_b = pd.notna(mean_b) and pd.notna(ir_b) and (abs(mean_b) >= 0.03) and (abs(ir_b) >= 0.5)

            if pass_a or pass_b:
                aktif_donem = "Dönem A (Negatif Faiz)" if pass_a else "Dönem B (Pozitif Faiz)"
                if pass_a and pass_b:
                    aktif_donem = "Hem Dönem A hem Dönem B"
                karar = "⚠️ KOŞULLU KABUL (REJİM)"
                gerekce = f"Aggregate sınırda ama {aktif_donem} rejiminde güçlü (|IC|>=0.03, IR>=0.5)."
            else:
                karar = "❌ RED (REJİMDE DE BAŞARISIZ)"
                gerekce = f"Aggregate sınırda (|IC|={abs_ic:.4f}, IR={ic_ir:.2f}) ve ne Dönem A ne B rejim eşiğini geçemedi."

        results.append({
            "feature": c,
            "mean_ic": mean_ic,
            "std_ic": std_ic,
            "ic_ir": ic_ir,
            "p_val": p_val,
            "mean_a": mean_a,
            "ir_a": ir_a,
            "mean_b": mean_b,
            "ir_b": ir_b,
            "karar": karar,
            "gerekce": gerekce,
            "exp_sign": exp_sign,
        })

    df_res = pd.DataFrame(results)

    print("\n" + "=" * 125)
    print(f"{'Feature Adı':<18} | {'Tüm Örneklem IC':<16} | {'IC-IR':<8} | {'p-değeri':<9} | {'Dönem A (IC/IR)':<18} | {'Dönem B (IC/IR)':<18} | {'Karar':<22}")
    print("-" * 125)
    for _, r in df_res.iterrows():
        a_str = f"{r['mean_a']:+.3f} / {r['ir_a']:.2f}" if pd.notna(r['mean_a']) else "N/A"
        b_str = f"{r['mean_b']:+.3f} / {r['ir_b']:.2f}" if pd.notna(r['mean_b']) else "N/A"
        print(f"{r['feature']:<18} | {r['mean_ic']:>+10.4f} (std={r['std_ic']:.3f}) | {r['ic_ir']:>+6.2f} | {r['p_val']:>7.4f}  | {a_str:<18} | {b_str:<18} | {r['karar']:<22}")
    print("=" * 125)

    print("\n" + "DETAYLI GEREKÇELER:")
    for _, r in df_res.iterrows():
        print(f"  • {r['feature']:<18}: {r['karar']} -> {r['gerekce']}")

    # JSON Olarak Kaydet
    output_path = ROOT_DIR / "reports" / "faz1_ic_sonuclari.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_res.to_json(output_path, orient="records", indent=2)
    print(f"\n✅ Sonuçlar kaydedildi: {output_path}")

    return df_res


if __name__ == "__main__":
    run_faz1_ic_screening()
