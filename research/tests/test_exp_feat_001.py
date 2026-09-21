from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RESEARCH))
import exp_feat_001 as feat
import exp_tgt_001 as t1
import exp_tgt_002 as t2


def synthetic_view(n=400):
    idx=pd.bdate_range("2020-01-01",periods=n)
    close=pd.Series(1.01**np.arange(n),index=idx)
    return pd.DataFrame({"research_close":close,"raw_close":close,"volume":100.0,
                         "economic_return":close.pct_change(fill_method=None),"trading_eligible":True,
                         "price_quality":"PROVIDER_ONLY"},index=idx)


class PriceFeatureDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract=json.loads(feat.CONTRACT_PATH.read_text(encoding="utf-8"))
        old=json.loads(feat.TGT1_CONTRACT.read_text(encoding="utf-8"))
        tc=json.loads(feat.TGT2_CONTRACT.read_text(encoding="utf-8"))
        cls.calendar,cls.symbols,cls.views,cls.benchmark=t1.load_inputs(old)
        cls.base_features,cls.raw,cls.raw_cov=t1.build_dataset(cls.calendar,cls.symbols,cls.views)
        cls.targets,_,_,_=t2.build_target_data(tc,cls.calendar,cls.symbols,cls.views,cls.benchmark,cls.base_features,cls.raw,cls.raw_cov)
        cls.features,cls.long=feat.build_feature_wave(cls.contract,cls.calendar,cls.base_features,cls.views)

    def test_all_25_feature_formulas_are_present_and_locked(self):
        expected={x["name"] for x in self.contract["candidates"]}
        values=feat.candidate_raw_values(synthetic_view(),399)
        self.assertEqual(len(expected),25); self.assertEqual(set(values),expected)
        for name in expected: self.assertTrue(np.isfinite(values[name]),name)
        for n in (5,10,20,40,63,126,252):
            name={5:"ret_5",10:"ret_10",20:"mom_20",40:"mom_40",63:"mom_63_rank",126:"mom_126",252:"mom_252"}[n]
            self.assertAlmostEqual(values[name],1.01**n-1,places=10)
        self.assertAlmostEqual(values["mom_126_skip20"],1.01**126-1,places=10)
        self.assertAlmostEqual(values["mom_252_skip20"],1.01**252-1,places=10)
        self.assertEqual(values["positive_return_ratio_63"],1.0)
        self.assertEqual(values["sign_consistency_4x20"],1.0)
        self.assertAlmostEqual(values["volume_cv63"],0.0)

    def test_rolling_boundaries_minimum_history_and_missing_not_zero(self):
        short=synthetic_view(20)
        values=feat.candidate_raw_values(short,19)
        self.assertTrue(np.isnan(values["mom_20"]))
        self.assertTrue(np.isnan(values["vol_20"]))
        self.assertTrue(np.isnan(values["log_adv63"]))
        self.assertNotEqual(values["mom_20"],0.0)
        enough=feat.candidate_raw_values(synthetic_view(21),20)
        self.assertTrue(np.isfinite(enough["mom_20"]))

    def test_no_future_data_for_each_feature(self):
        view=synthetic_view(); before=feat.candidate_raw_values(view,300)
        changed=view.copy(deep=True); changed.iloc[301:,changed.columns.get_loc("research_close")]=10**12
        changed.iloc[301:,changed.columns.get_loc("raw_close")]=10**12
        changed.iloc[301:,changed.columns.get_loc("volume")]=10**12
        after=feat.candidate_raw_values(changed,300)
        for name in before:
            if np.isnan(before[name]): self.assertTrue(np.isnan(after[name]),name)
            else: self.assertEqual(before[name],after[name],name)

    def test_cross_sectional_percentile_rank_is_same_date_only_and_deterministic(self):
        for (date,candidate),g in self.long.groupby(["signal_date","candidate"]):
            expected=g.raw_value.rank(pct=True,method="average")
            np.testing.assert_allclose(g.feature_value,expected,equal_nan=True)
            self.assertNotIn("XU100.IS",set(g.symbol))
        self.assertEqual(len(self.symbols),88)

    def test_volume_eligibility_and_sasa_unresolved_rows(self):
        sasa=self.views["SASA.IS"]
        bad=np.flatnonzero(sasa.price_quality.fillna("UNRESOLVED").astype(str).eq("UNRESOLVED").to_numpy())
        self.assertGreater(len(bad),0)
        pos=min(max(int(bad[0])+70,300),len(sasa)-1)
        before=feat.candidate_raw_values(sasa,pos)
        changed=sasa.copy(deep=True)
        changed.iloc[bad,changed.columns.get_loc("volume")]=10**15
        after=feat.candidate_raw_values(changed,pos)
        for name in ("log_adv20","log_adv63","log_amihud20","log_amihud63","volume_cv63"):
            if np.isnan(before[name]): self.assertTrue(np.isnan(after[name]))
            else: self.assertEqual(before[name],after[name],name)

    def test_train_only_preprocessing(self):
        data=self.targets.merge(self.features,on=["signal_date","symbol",*feat.BASE_COLS],how="left")
        tr=feat.train_rows(data,"RAW",20,"2023-01-01"); va=feat.valid_rows(data,"RAW",20,"2023-01-01","2023-12-31").copy()
        model=feat.fit(tr,feat.BASE_COLS+["mom_20"])
        med=model.med.copy(); mean=model.mean.copy(); scale=model.scale.copy()
        va["mom_20"]=10**9
        feat.predict(model,va)
        np.testing.assert_array_equal(model.med,med); np.testing.assert_array_equal(model.mean,mean); np.testing.assert_array_equal(model.scale,scale)

    def test_baseline_target_horizon_is_frozen_and_outer_isolation(self):
        sel=pd.read_csv(feat.RESULTS/"EXP-FEAT-001_inner_selection.csv")
        out=pd.read_csv(feat.RESULTS/"EXP-FEAT-001_outer_incremental.csv")
        self.assertTrue(out.was_inner_selected.all())
        merged=out.merge(sel[sel.selected_inner][["outer_fold","candidate","frozen_target_family","frozen_horizon"]],on=["outer_fold","candidate"])
        self.assertTrue((merged.target_family==merged.frozen_target_family).all())
        self.assertTrue((merged.horizon_sessions==merged.frozen_horizon).all())
        old=json.loads(feat.TGT1_CONTRACT.read_text(encoding="utf-8"))
        data=self.targets.merge(self.features,on=["signal_date","symbol",*feat.BASE_COLS],how="left")
        for fold in old["outer_folds"]:
            for family in t2.FAMILIES:
                for h in t2.HORIZONS:
                    tr=feat.train_rows(data,family,h,fold["test_start"])
                    self.assertTrue((tr.label_end<pd.Timestamp(fold["test_start"])).all())

    def test_no_macro_or_fundamental(self):
        self.assertEqual(self.contract["data_scope"]["macro_including_usdtry"],"EXCLUDED")
        self.assertEqual(self.contract["data_scope"]["fundamental_including_recovered_exact"],"EXCLUDED")
        names={x["name"] for x in self.contract["candidates"]}
        self.assertTrue(names.isdisjoint(set(self.contract["forbidden_inputs"])))

    def test_reproducibility(self):
        data=self.targets.merge(self.features,on=["signal_date","symbol",*feat.BASE_COLS],how="left")
        tr=feat.train_rows(data,"RAW",20,"2023-01-01")
        one=feat.fit(tr,feat.BASE_COLS+["log_adv20"]); two=feat.fit(tr,feat.BASE_COLS+["log_adv20"])
        np.testing.assert_array_equal(feat.predict(one,tr.head(100)),feat.predict(two,tr.head(100)))


if __name__=="__main__": unittest.main()
