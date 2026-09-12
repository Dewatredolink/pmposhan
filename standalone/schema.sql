PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS app_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS local_users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  role TEXT NOT NULL CHECK (role IN ('SYSTEM_ADMIN','HEADMASTER','TEACHER')),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS installation_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  installation_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  app_version TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS license_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  license_json TEXT,
  signature_b64 TEXT,
  activated_at TEXT,
  last_validated_at TEXT
);

CREATE TABLE IF NOT EXISTS districts (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blocks (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  district_id TEXT NOT NULL REFERENCES districts(id) ON DELETE RESTRICT,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clusters (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE RESTRICT,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schools (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  udise_code TEXT NOT NULL UNIQUE,
  cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  village TEXT,
  class_1_5_strength INTEGER NOT NULL DEFAULT 0,
  class_6_8_strength INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS academic_years (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (start_date <= end_date)
);

CREATE TABLE IF NOT EXISTS ingredients (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  category TEXT NOT NULL,
  base_unit TEXT NOT NULL,
  reorder_level REAL NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
  safety_stock REAL NOT NULL DEFAULT 0 CHECK (safety_stock >= 0),
  track_inventory INTEGER NOT NULL DEFAULT 1 CHECK (track_inventory IN (0,1)),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS menus (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  week_pattern TEXT NOT NULL,
  day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 6),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipes (
  id TEXT PRIMARY KEY,
  menu_id TEXT NOT NULL REFERENCES menus(id) ON DELETE RESTRICT,
  ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
  student_group TEXT NOT NULL CHECK (student_group IN ('CLASS_1_5','CLASS_6_8','ALL')),
  qty_per_student REAL NOT NULL CHECK (qty_per_student >= 0),
  measurement_unit TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (menu_id, ingredient_id, student_group, effective_from),
  CHECK (effective_to IS NULL OR effective_from <= effective_to)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  user_id TEXT REFERENCES local_users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  details_json TEXT
);

CREATE TABLE IF NOT EXISTS backup_history (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  file_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  sha256 TEXT,
  size_bytes INTEGER,
  status TEXT NOT NULL CHECK (status IN ('CREATED','VERIFIED','FAILED','RESTORED')),
  notes TEXT
);

CREATE INDEX IF NOT EXISTS ix_blocks_district_id ON blocks(district_id);
CREATE INDEX IF NOT EXISTS ix_clusters_block_id ON clusters(block_id);
CREATE INDEX IF NOT EXISTS ix_schools_cluster_id ON schools(cluster_id);
CREATE INDEX IF NOT EXISTS ix_schools_udise ON schools(udise_code);
CREATE INDEX IF NOT EXISTS ix_academic_years_dates ON academic_years(start_date, end_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_year_current ON academic_years(is_current) WHERE is_current = 1;
CREATE INDEX IF NOT EXISTS ix_ingredients_active_name ON ingredients(active, name_en);
CREATE INDEX IF NOT EXISTS ix_menus_day_code ON menus(day_of_week, code);
CREATE INDEX IF NOT EXISTS ix_recipes_lookup ON recipes(menu_id, ingredient_id, student_group, effective_from);
CREATE INDEX IF NOT EXISTS ix_audit_occurred_at ON audit_log(occurred_at);
