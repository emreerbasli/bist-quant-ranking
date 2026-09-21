import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import pandas as pd

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "research"))

# Create a mock for runner_data_sources
mock_runner_module = MagicMock()
mock_data_sources = MagicMock()
mock_benchmark = MagicMock()
mock_benchmark.index = pd.DatetimeIndex(["2026-09-16", "2026-09-17", "2026-09-18"])
mock_data_sources.benchmark.return_value = mock_benchmark
mock_runner_module.CanonicalRunnerDataSources.return_value = mock_data_sources
sys.modules['runner_data_sources'] = mock_runner_module

# Create a mock for forward_infrastructure_001r3
mock_fw_module = MagicMock()
sys.modules['forward_infrastructure_001r3'] = mock_fw_module

# Import the orchestrator after mocking
with patch("schedule.every"):
    from run_paper_trader import calistir_hibrid_motor_sirali

class TestDailyOrchestration(unittest.TestCase):
    @patch("run_paper_trader.periyodik_gorev_calistir", return_value=True)
    @patch("subprocess.run")
    @patch("shadow_reader.get_shadow_system_state")
    def test_successful_orchestration(self, mock_state, mock_subprocess, mock_v3):
        # 4. Actual eligible date is determined
        mock_fw_module.actual_signal_date.return_value.date.return_value = "2026-09-18"
        
        # 10. New COMMITTED -> Telegram eligible
        # First call (at step 3) returns different session so it proceeds.
        # Second call (at step 5) returns OFFICIAL_CLEAN_FORWARD and matching session, triggering telegram.
        mock_state.side_effect = [
            {"status": "OFFICIAL_CLEAN_FORWARD", "session_date": "2026-09-17"},
            {"status": "OFFICIAL_CLEAN_FORWARD", "session_date": "2026-09-18"}
        ]
        
        calistir_hibrid_motor_sirali(force=True, send_telegram=True)
        
        # 1. V3 orchestration still called
        mock_v3.assert_called_once()
        
        # 2. Prospective steps called in correct order
        calls = mock_subprocess.call_args_list
        self.assertTrue(any("prospective_acquisition_phase_ab.py" in str(c) for c in calls))
        self.assertTrue(any("prospective_kap_corporate_actions.py" in str(c) for c in calls))
        self.assertTrue(any("prospective_canonical_extension.py" in str(c) for c in calls))
        
        # 6. & 7. Eligible session -> LGBMR & LambdaMART processing
        self.assertTrue(any("RC-LGBMR-001" in str(c) and "run_frozen_shadow.py" in str(c) for c in calls))
        self.assertTrue(any("RC-LAMBDAMART-001" in str(c) and "run_frozen_shadow.py" in str(c) for c in calls))
        
        # 4. Calendar today not assumed (it passed "2026-09-18")
        self.assertTrue(any("2026-09-18" in str(c) for c in calls if "run_frozen_shadow.py" in str(c)))
        
        # 10. Telegram eligible
        self.assertTrue(any("shadow_telegram.py" in str(c) for c in calls))

    @patch("run_paper_trader.periyodik_gorev_calistir", return_value=True)
    @patch("subprocess.run")
    def test_prospective_failure_blocks_rc(self, mock_subprocess, mock_v3):
        import subprocess
        # Mock failure in first prospective script
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "cmd")
        
        calistir_hibrid_motor_sirali(force=True, send_telegram=True)
        
        # 1. V3 orchestration still called
        mock_v3.assert_called_once()
        
        # 3. Prospective failure -> RC processing blocked (run_frozen_shadow never called)
        calls = mock_subprocess.call_args_list
        self.assertFalse(any("run_frozen_shadow.py" in str(c) for c in calls))

    @patch("run_paper_trader.periyodik_gorev_calistir", return_value=True)
    @patch("subprocess.run")
    @patch("shadow_reader.get_shadow_system_state")
    def test_no_new_eligible_session_is_noop(self, mock_state, mock_subprocess, mock_v3):
        mock_fw_module.actual_signal_date.return_value.date.return_value = "2026-09-18"
        
        # 5. No eligible session (because it's already processed) -> Clean NO-OP
        mock_state.return_value = {"status": "OFFICIAL_CLEAN_FORWARD", "session_date": "2026-09-18"}
        
        calistir_hibrid_motor_sirali(force=True, send_telegram=True)
        
        calls = mock_subprocess.call_args_list
        self.assertFalse(any("run_frozen_shadow.py" in str(c) for c in calls))
        self.assertFalse(any("shadow_telegram.py" in str(c) for c in calls))
        
    @patch("run_paper_trader.periyodik_gorev_calistir", return_value=True)
    @patch("subprocess.run")
    @patch("shadow_reader.get_shadow_system_state")
    def test_processing_failure_blocks_telegram(self, mock_state, mock_subprocess, mock_v3):
        import subprocess
        mock_fw_module.actual_signal_date.return_value.date.return_value = "2026-09-18"
        
        # Step 3 state check (not processed)
        # Step 5 state check (processing failed, so state is not updated)
        mock_state.side_effect = [
            {"status": "OFFICIAL_CLEAN_FORWARD", "session_date": "2026-09-17"},
            {"status": "OFFICIAL_CLEAN_FORWARD", "session_date": "2026-09-17"}
        ]
        
        # Let prospective pass, but processing fail
        def subprocess_side_effect(*args, **kwargs):
            if "run_frozen_shadow.py" in args[0]:
                raise subprocess.CalledProcessError(1, "cmd")
            return MagicMock()
        mock_subprocess.side_effect = subprocess_side_effect
        
        calistir_hibrid_motor_sirali(force=True, send_telegram=True)
        
        calls = mock_subprocess.call_args_list
        # 8. Candidate processing failure -> Telegram blocked
        # 9. No new COMMITTED -> Telegram blocked
        self.assertFalse(any("shadow_telegram.py" in str(c) for c in calls))
        
    @patch("run_paper_trader.periyodik_gorev_calistir", return_value=True)
    @patch("subprocess.run")
    @patch("shadow_reader.get_shadow_system_state")
    def test_dry_run_blocks_telegram(self, mock_state, mock_subprocess, mock_v3):
        mock_fw_module.actual_signal_date.return_value.date.return_value = "2026-09-18"
        
        # 11. Dry-run -> Telegram blocked
        mock_state.side_effect = [
            {"status": "VALIDATED_DRY_RUN", "session_date": "2026-09-17"},
            {"status": "VALIDATED_DRY_RUN", "session_date": "2026-09-18"}
        ]
        
        calistir_hibrid_motor_sirali(force=True, send_telegram=True)
        
        calls = mock_subprocess.call_args_list
        self.assertFalse(any("shadow_telegram.py" in str(c) for c in calls))

if __name__ == '__main__':
    unittest.main()
