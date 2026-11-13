-- MySQL 8 schema for the Defect Rate Trend Analysis and Root Cause Identification System
CREATE DATABASE IF NOT EXISTS defect_qc CHARACTER SET utf8mb4;
USE defect_qc;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(60) NOT NULL UNIQUE,
  full_name VARCHAR(120) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('QC Engineer','Line Supervisor','Quality Manager','IT Administrator') NOT NULL,
  email VARCHAR(120) NULL,
  assigned_line VARCHAR(30) NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  status ENUM('pending','active','rejected') NOT NULL DEFAULT 'active',
  failed_logins INT NOT NULL DEFAULT 0,
  locked_until DATETIME NULL,
  token_version INT NOT NULL DEFAULT 1,
  last_login_at DATETIME NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE defect_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  inspection_date DATE NOT NULL,
  production_line VARCHAR(30) NOT NULL,
  product_type VARCHAR(40) NOT NULL,
  shift VARCHAR(20) NOT NULL,
  machine_id VARCHAR(20) NOT NULL,
  defect_type VARCHAR(40) NOT NULL,
  batch_number VARCHAR(40) NOT NULL,
  severity ENUM('None','Minor','Major','Critical','Safety-Critical') NOT NULL,
  units_inspected INT NOT NULL CHECK (units_inspected > 0),
  defect_count INT NOT NULL CHECK (defect_count >= 0),
  temperature FLOAT, humidity FLOAT, machine_age_months INT,
  root_cause ENUM('Man','Machine','Material','Method','Environment') NULL,
  created_by INT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT chk_count_le_units CHECK (defect_count <= units_inspected),
  FOREIGN KEY (created_by) REFERENCES users(id),
  INDEX idx_date (inspection_date), INDEX idx_line (production_line),
  INDEX idx_machine (machine_id), INDEX idx_type (defect_type), INDEX idx_batch (batch_number)
);

CREATE TABLE audit_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  action VARCHAR(60) NOT NULL,
  detail VARCHAR(255),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE thresholds (
  id INT AUTO_INCREMENT PRIMARY KEY,
  production_line VARCHAR(30) NOT NULL,
  product_type VARCHAR(40) NULL,
  max_defect_rate FLOAT NOT NULL CHECK (max_defect_rate > 0 AND max_defect_rate <= 1),
  updated_by INT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE TABLE alerts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  kind ENUM('threshold','safety') NOT NULL,
  production_line VARCHAR(30) NOT NULL, product_type VARCHAR(40) NULL,
  record_id INT NULL, defect_rate FLOAT NULL, threshold FLOAT NULL,
  message VARCHAR(255) NOT NULL,
  email_status VARCHAR(20) NOT NULL DEFAULT 'none', email_attempts INT NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  acknowledged_by INT NULL, acknowledged_at DATETIME NULL,
  FOREIGN KEY (acknowledged_by) REFERENCES users(id)
);

CREATE TABLE corrective_actions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  production_line VARCHAR(30) NOT NULL, machine_id VARCHAR(20) NULL, defect_type VARCHAR(40) NULL,
  root_cause ENUM('Man','Machine','Material','Method','Environment') NOT NULL,
  suggested_cause ENUM('Man','Machine','Material','Method','Environment') NULL,
  description VARCHAR(500) NOT NULL,
  status ENUM('Proposed','Approved','Implemented') NOT NULL DEFAULT 'Proposed',
  logged_by INT NULL, approved_by INT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP, implemented_at DATE NULL,
  FOREIGN KEY (logged_by) REFERENCES users(id), FOREIGN KEY (approved_by) REFERENCES users(id)
);

CREATE TABLE sus_responses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL, role VARCHAR(30) NOT NULL,
  answers VARCHAR(60) NOT NULL, score FLOAT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
