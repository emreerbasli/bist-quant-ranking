from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))
import exp_tgt_001 as base
import exp_tgt_002 as tgt
from temporal_validation import build_label_interval


class TargetFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract=json.loads(tgt.CONTRACT_PATH.read_text(encoding="utf-8"))
        old=json.loads(tgt.TGT1_CONTRACT.read_text(encoding="utf-8"))
        cls.calendar,cls.symbols,cls.views,cls.benchmark=base.load_inputs(old)
        cls.features,cls.raw,cls.raw_cov=base.build_dataset(cls.calendar,cls.symbols,cls.views)
        cls.targets,cls.coverage,cls.betas,cls.mapping=tgt.build_target_data(cls.contract,cls.calendar,cls.symbols,cls.views,cls.benchmark,cls.features,cls.raw,cls.raw_cov)

    def test_target_formulas(self):
        for family in tgt.FAMILIES:
            self.assertGreater(len(self.targets[self.targets.target_family.eq(family)]),0)
        row=self.targets[self.targets.target_family.eq("SECTOR_RELATIVE")].iloc[0]
        self.assertAlmostEqual(row.target_value,row.raw_forward_return-row.sector_reference)
        row=self.targets[self.targets.target_family.eq("BETA_RESIDUAL")].iloc[0]
        self.assertAlmostEqual(row.target_value,row.raw_forward_return-row.ex_ante_beta*row.benchmark_forward_return)
        row=self.targets[self.targets.target_family.eq("VOL_SCALED")].iloc[0]
        self.assertAlmostEqual(row.target_value,row.raw_forward_return/row.vol_scale)

    def test_sector_mapping_is_fixed_and_no_future_reassignment(self):
        self.assertEqual(set(self.mapping),set(self.symbols))
        self.assertFalse(self.contract["sector_contract"]["future_reassignment_allowed"])
        for symbol in self.symbols[:10]: self.assertEqual(self.mapping[symbol],tgt.cfg.HISSE_SEKTOR.get(symbol,"UNCLASSIFIED"))

    def test_beta_estimation_uses_no_future(self):
        symbol=self.symbols[0]; pos=600
        before=tgt.estimate_beta(self.views[symbol],self.benchmark,pos)
        changed=self.views[symbol].copy(deep=True)
        changed.iloc[pos+1:,changed.columns.get_loc("research_close")]=10**9
        after=tgt.estimate_beta(changed,self.benchmark,pos)
        self.assertEqual(before,after)

    def test_volatility_scaling_uses_pre_signal_feature(self):
        vol=self.targets[self.targets.target_family.eq("VOL_SCALED")]
        self.assertTrue((vol.vol_scale>=self.contract["volatility_contract"]["daily_vol_floor"]).all())
        self.assertTrue((vol.vol_scale<=self.contract["volatility_contract"]["daily_vol_cap"]).all())
        self.assertFalse(self.contract["volatility_contract"]["forward_volatility_allowed"])

    def test_dynamic_labels_20_40_60(self):
        signal=self.calendar[300]
        for h in tgt.HORIZONS:
            interval=build_label_interval(self.calendar,signal,h)
            self.assertEqual(self.calendar.get_loc(interval.label_end)-self.calendar.get_loc(interval.label_start),h)

    def test_horizon_is_inner_only_and_outer_isolated(self):
        selections=pd.read_csv(tgt.RESULTS/"EXP-TGT-002_inner_selections.csv")
        outer=pd.read_csv(tgt.RESULTS/"EXP-TGT-002_outer_metrics.csv")
        self.assertEqual(len(selections),4)
        self.assertFalse(self.contract["outer_horizon_feedback"])
        for family in tgt.FAMILIES:
            col=f"{family.lower()}_selected_horizon"
            self.assertTrue(set(selections[col]).issubset({20,40,60}))
            merged=outer[outer.target_family.eq(family)][["outer_fold","inner_selected_horizon"]].drop_duplicates().merge(selections[["outer_fold",col]],on="outer_fold")
            self.assertTrue((merged.inner_selected_horizon==merged[col]).all())

    def test_same_features_and_model_across_families(self):
        self.assertEqual(self.contract["features"],base.FEATURES)
        self.assertTrue(self.contract["model"]["same_across_target_families"])
        self.assertEqual(self.contract["model"]["alpha"],1.0)

    def test_no_macro_or_fundamental(self):
        self.assertEqual(self.contract["data_scope"]["fundamental"],"EXCLUDED")
        self.assertEqual(self.contract["data_scope"]["macro_including_usdtry"],"EXCLUDED")
        self.assertTrue(set(self.contract["features"]).isdisjoint(set(self.contract["forbidden_inputs"])))

    def test_reproducibility(self):
        rows=tgt.training_rows(self.targets,"RAW",20,"2023-01-01")
        one=base.fit_ridge(rows); two=base.fit_ridge(rows)
        np.testing.assert_array_equal(base.predict(one,rows.head(50)),base.predict(two,rows.head(50)))

    def test_coverage_and_daily_nav_outputs(self):
        self.assertEqual(set(self.coverage.target_family),set(tgt.FAMILIES))
        nav=pd.read_csv(tgt.RESULTS/"EXP-TGT-002_daily_nav.csv")
        self.assertGreater(len(nav),0); self.assertIn("nav",nav.columns)


if __name__=="__main__": unittest.main()
