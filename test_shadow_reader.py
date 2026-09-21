import sys
from pathlib import Path

# Add bist-bot directory to sys.path
root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

from shadow_reader import get_shadow_system_state

state = get_shadow_system_state()
print("State:", state)

if state is None:
    print("TEST FAIL: No state returned.")
    sys.exit(1)

if state["status"] == "VALIDATED_DRY_RUN":
    print("TEST PASS: Correctly fell back to dry run.")
    print(f"Primary Top 1: {state['primary']['ordered_top10'][0]['ticker']}")
    print(f"Secondary Top 1: {state['secondary']['ordered_top10'][0]['ticker']}")
else:
    print(f"TEST FAIL: Expected VALIDATED_DRY_RUN, got {state['status']}")
