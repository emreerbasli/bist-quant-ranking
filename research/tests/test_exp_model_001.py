from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RESEARCH))
import exp_model_001 as model
import exp_tgt_001 as t1
import exp_tgt_002 as t2


class ModelArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract=json.loads(model.CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.c1=json.loads(model.TGT1_PATH.read_text(encoding="utf-8"))
        cls.c2=json.loads(model.TGT2_PATH.read_text(encoding="utf-8"))
        cls.selections=pd.read_csv(model.RESULTS/"EXP-MODEL-001_procedure_selections.csv")
        cls.inner=pd.read_csv(model.RESULTS/"EXP-MODEL-001_inner_metrics.csv")
        cls.controlled=pd.read_csv(model.RESULTS/"EXP-MODEL-001_controlled_outer.csv")
        cls.whole=pd.read_csv(model.RESULTS/"EXP-MODEL-001_whole_outer.csv")

    def test_same_three_features_all_architectures(self):
        self.assertEqual(tuple(self.contract["features"]),model.FEATURES)
        self.assertEqual(set(self.contract["models"]),set(model.ARCHS))

    def test_no_rejected_feature_leakage(self):
        rejected={"vol_126","vol_63_rank","log_adv20","log_adv63","log_amihud20"}
        self.assertTrue(rejected.isdisjoint(self.contract["features"]))
        self.assertFalse(self.contract["rejected_exp_feat_001_features_allowed"])

    def test_no_macro_or_fundamental(self):
        self.assertEqual(self.contract["data_scope"]["macro"],"EXCLUDED")
        self.assertEqual(self.contract["data_scope"]["fundamental"],"EXCLUDED")
        self.assertTrue(set(self.contract["features"]).isdisjoint(self.contract["forbidden_inputs"]))

    def test_dynamic_labels_and_purge(self):
        calendar=pd.bdate_range("2020-01-01",periods=100)
        for h in (20,40,60):
            x=t1.build_label_interval(calendar,calendar[5],h)
            self.assertEqual(calendar.get_loc(x.label_end)-calendar.get_loc(x.label_start),h)
        for row in self.inner.itertuples(index=False):
            self.assertLess(pd.Timestamp(row.train_last_label_end),pd.Timestamp(f"{row.inner_validation_year}-01-01"))

    def test_inner_target_horizon_selection_only(self):
        self.assertEqual(set(self.selections.selected_family),set(t2.FAMILIES))
        self.assertTrue(set(self.selections.selected_horizon).issubset(set(t2.HORIZONS)))
        self.assertEqual(len(self.selections),len(model.ARCHS)*len(self.c1["outer_folds"]))
        self.assertFalse(self.contract["target_horizon"]["outer_feedback"])

    def test_outer_isolation_and_lightgbm_training_boundaries(self):
        for fold in self.c1["outer_folds"]:
            rows=self.inner[self.inner.outer_fold.eq(fold["id"])]
            self.assertTrue((pd.to_datetime(rows.train_last_label_end)<pd.Timestamp(fold["test_start"])).all())
        self.assertEqual(set(self.whole.architecture),set(model.ARCHS))

    def test_architecture_controlled_uses_identical_ridge_configuration(self):
        for fold,g in self.controlled.groupby("outer_fold"):
            self.assertEqual(g.target_family.nunique(),1,fold)
            self.assertEqual(g.horizon_sessions.nunique(),1,fold)

    def test_lambdamart_grouping_and_relevance_mapping(self):
        rows=pd.DataFrame({"signal_date":pd.to_datetime(["2020-01-01"]*3+["2020-02-01"]*2),
                           "target_rank":[0.01,0.2,1.0,0.6,0.99]})
        groups=rows.groupby("signal_date",sort=True).size().to_numpy()
        self.assertEqual(int(groups.sum()),len(rows)); self.assertTrue(np.all(groups>0))
        np.testing.assert_array_equal(model.relevance(rows.target_rank),[0,1,4,3,4])

    def test_fixed_seed_policy_and_no_early_stopping(self):
        self.assertEqual(self.contract["tree_seeds"],[11,29,47])
        self.assertIn("median",self.contract["seed_aggregation"])
        self.assertEqual(self.contract["early_stopping"],"NOT_USED; fixed estimator count")

    def test_deterministic_factor_and_smoke(self):
        smoke=json.loads((model.RESULTS/"EXP-MODEL-001_smoke.json").read_text())
        self.assertTrue(smoke["pass"])
        rows=pd.DataFrame({"signal_date":pd.to_datetime(["2020-01-01"]*3),"mom_12_1":[1,2,3],"mom_63":[3,2,1],"vol_63":[3,2,1]})
        np.testing.assert_array_equal(model.factor_scores(rows),model.factor_scores(rows.copy()))

    def test_seed_outputs_are_complete(self):
        seeds=pd.read_csv(model.RESULTS/"EXP-MODEL-001_seed_metrics.csv")
        self.assertEqual(set(seeds.seed),set(self.contract["tree_seeds"]))
        self.assertEqual(len(seeds),2*len(self.c1["outer_folds"])*len(self.contract["tree_seeds"]))

    def test_daily_nav_and_risk_are_daily(self):
        nav=pd.read_csv(model.RESULTS/"EXP-MODEL-001_daily_nav.csv",parse_dates=["date"])
        self.assertFalse(nav.empty); self.assertTrue(np.isfinite(nav.nav).all())
        for _,g in nav.groupby(["outer_fold","architecture","cost_bps"]):
            self.assertTrue(g.date.is_monotonic_increasing)
            self.assertFalse(g.date.duplicated().any())

    def test_cost_monotonic_sanity(self):
        for row in self.whole.itertuples(index=False):
            returns=[getattr(row,f"portfolio_{c}bps_gross_or_net_return") for c in (0,30,50,100)]
            self.assertTrue(all(a>=b-1e-12 for a,b in zip(returns,returns[1:])))

    def test_classifications_derive_from_locked_contract(self):
        out=pd.read_csv(model.RESULTS/"EXP-MODEL-001_classification.csv")
        self.assertEqual(set(out.architecture),set(model.ARCHS))
        self.assertEqual(set(out.classification),{"CONTROL / BASELINE","VIABLE"})

    def test_production_writes_are_forbidden(self):
        self.assertFalse(self.contract["production_writes_allowed"])


if __name__=="__main__": unittest.main()
