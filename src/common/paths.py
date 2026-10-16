from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONF_DIR = ROOT / "conf"
SEED_DIR = ROOT / "data" / "seed"
FIXTURE_DIR = ROOT / "data" / "dq_fixtures"
GENERATED_DIR = ROOT / "data" / "generated"
DEFAULT_DUCKDB = GENERATED_DIR / "carestaff.duckdb"
DQ_RULES_PATH = CONF_DIR / "dq_rules.yaml"
MLRUNS_DIR = ROOT / "mlruns"
MODEL_DIR = GENERATED_DIR / "models"
MLFLOW_DB = GENERATED_DIR / "mlflow.db"
