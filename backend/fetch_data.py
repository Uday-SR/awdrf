"""One-off: download Jan-2026 Elexon data into backend/data/ (commit the output)."""
import os

from app import elexon

out = elexon.DATA_DIR
os.makedirs(out, exist_ok=True)
elexon.fetch_actuals().to_csv(os.path.join(out, "actuals.csv.gz"), index=False)
elexon.fetch_forecasts().to_csv(os.path.join(out, "forecasts.csv.gz"), index=False)
print("Saved to", os.path.abspath(out))
