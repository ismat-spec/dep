"""
EG2A17 - Shared configuration for the whole pipeline.
Every other script imports its settings from here, so you only change
things in ONE place.
"""

# ===== BLE (must match the Arduino sketch) =====
SERVICE_UUID    = "ebc35177-c71a-444a-967e-464ca94df0f1"
ACCELNGYRO_UUID = "f509416c-3c4b-401e-a768-b25a9e621a91"
DEFAULT_DEVICE  = "Ismat_Group4"

# ===== Storage backend =====
# "sqlite"  -> zero-setup single file (reliable fallback)
# "mariadb" -> real database server (main, more marks for scalability)
DB_BACKEND = "mariadb"

# SQLite settings
SQLITE_PATH = "nesso_data.db"

# MariaDB settings  (change PASSWORD to what you set during install)
MARIADB = {
    "host":     "127.0.0.1",
    "port":     3307,          # matches your MariaDB install
    "user":     "nesso",
    "password": "nesso_pw",
    "database": "nesso_db",
}

# ===== Sampling =====
SAMPLE_RATE_HZ = 100          # matches the Arduino sketch
FLUSH_EVERY    = 100          # write to DB every N samples (~1 s)

# ===== Validation limits (BMI270 sensor ranges) =====
MAX_ACC_G   = 16.0
MAX_GYR_DPS = 2000.0

# ===== Fall / trip detection thresholds =====
# Acceleration magnitude at rest is ~1 g. A fall shows a free-fall dip
# (low g) followed by an impact spike (high g), then unusual stillness.
# These are literature-based starting values -- TUNE them with your own
# recorded data and record the final numbers in your report.
FREEFALL_G      = 0.7     # below this = possible free fall
IMPACT_G        = 1.8     # above this = possible impact
NEARMISS_GYR    = 350.0   # deg/s spike suggesting a stumble/lurch
FALL_WINDOW_S   = 1.5     # free-fall and impact must occur within this time
POST_IMPACT_S   = 1.0     # stillness window checked after an impact
STILL_G_BAND    = 0.4     # |mag-1g| below this = "still" (person on ground)