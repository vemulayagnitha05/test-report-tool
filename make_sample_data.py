"""
Makes data/sample_results.csv with SYNTHETIC (made up) test results, so the tool can be tried
without real data. The numbers are random, with a few problems planted on purpose:
  - 'throughput' suite gets worse in build_104 (a regression)
  - 'handover' and 'multi_stream' are flaky
  - 'latency_ms' is not capable, 'tx_power_dbm' is marginal
  - 'temp_c' drifts upwards in the last builds
"""
import numpy as np
import pandas as pd

rng = np.random.RandomState(42)

BUILDS = ["build_101", "build_102", "build_103", "build_104", "build_105", "build_106"]
RUNS_PER_BUILD = 3

# (suite, test, typical duration in ms)
PASS_FAIL_TESTS = [
    ("connectivity", "attach_time", 800), ("connectivity", "handover", 1500),
    ("connectivity", "reconnect", 1200), ("connectivity", "dns_lookup", 300),
    ("connectivity", "tls_handshake", 450), ("connectivity", "ping_loss", 2000),
    ("throughput", "dl_speed_check", 5000), ("throughput", "ul_speed_check", 5200),
    ("throughput", "multi_stream", 8000), ("throughput", "large_file", 12000),
    ("firmware", "update_flow", 20000), ("firmware", "rollback", 15000),
    ("firmware", "config_restore", 2500), ("firmware", "factory_reset", 4000),
    ("power", "standby_mode", 3000), ("power", "wake_up", 900),
]

# (suite, test, unit, mean, std, lower limit, upper limit, typical duration)
MEASURED_TESTS = [
    ("throughput", "latency_ms", "ms", 42, 4, None, 50, 700),
    ("power", "tx_power_dbm", "dBm", 21, 0.8, 18, 24, 1100),
    ("power", "current_ma", "mA", 120, 5, 100, 140, 1000),
    ("firmware", "boot_time_s", "s", 9, 1.0, None, 12, 9500),
    ("firmware", "temp_c", "C", 45, 3, 20, 60, 600),
]

rows = []
start = pd.Timestamp("2026-09-01 08:00")


def duration(typical):
    value = rng.lognormal(mean=np.log(typical), sigma=0.12)
    if rng.rand() < 0.04:
        value *= rng.uniform(3, 5)  # now and then a run is very slow
    return round(value, 1)


for b, build in enumerate(BUILDS):
    for run in range(RUNS_PER_BUILD):
        when = start + pd.Timedelta(days=b, hours=run * 3, minutes=int(rng.randint(0, 50)))

        for suite, name, typical in PASS_FAIL_TESTS:
            fail_chance = 0.02
            if name in ("handover", "multi_stream"):
                fail_chance = 0.30  # flaky
            if suite == "throughput" and build == "build_104":
                fail_chance = 0.60  # regression
            roll = rng.rand()
            if roll < 0.004:
                status = "error"
            elif roll < 0.004 + fail_chance:
                status = "fail"
            else:
                status = "pass"
            rows.append([name, suite, build, when, status, duration(typical), None, None, None, ""])

        for suite, name, unit, mean, std, low, high, typical in MEASURED_TESTS:
            shift = 0
            if name == "temp_c":
                shift = {4: 5, 5: 9}.get(b, 0)
            if name == "latency_ms" and build == "build_104":
                shift = 6
            value = round(rng.normal(mean + shift, std), 2)
            if rng.rand() < 0.005:
                rows.append([name, suite, build, when, "error", duration(typical), None, low, high, unit])
                continue
            bad = (low is not None and value < low) or (high is not None and value > high)
            rows.append([name, suite, build, when, "fail" if bad else "pass",
                         duration(typical), value, low, high, unit])

df = pd.DataFrame(rows, columns=["test_name", "suite", "build", "timestamp", "status",
                                 "duration_ms", "measurement", "lower_limit", "upper_limit", "unit"])
df.insert(0, "test_id", range(1, len(df) + 1))
df.to_csv("data/sample_results.csv", index=False)
print("wrote data/sample_results.csv with", len(df), "rows (synthetic data)")
