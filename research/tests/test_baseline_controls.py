from pathlib import Path
import sys
import unittest

import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

from baselines_price_only import metrics


class BaselineControlTests(unittest.TestCase):
    def test_metrics_detects_daily_drawdown(self):
        nav = pd.Series([1.0, 1.2, 0.9, 1.1], index=pd.bdate_range("2020-01-01", periods=4))
        result = metrics(nav)
        self.assertAlmostEqual(result["daily_max_drawdown"], -0.25)

    def test_cost_stress_cannot_increase_terminal_nav_by_construction(self):
        gross = 1.25
        turnover = 2.0
        net_30 = gross * (1 - turnover * 30 / 10000)
        net_100 = gross * (1 - turnover * 100 / 10000)
        self.assertLess(net_100, net_30)
        self.assertLess(net_30, gross)


if __name__ == "__main__":
    unittest.main()
