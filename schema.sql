-- Parking Slot Allocation System: MariaDB schema
CREATE DATABASE IF NOT EXISTS parking_db CHARACTER SET utf8mb4;
USE parking_db;

CREATE TABLE IF NOT EXISTS users (
  user_id       INT AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(50)  NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role          VARCHAR(10)  NOT NULL CHECK (role IN ('admin', 'operator'))
);

CREATE TABLE IF NOT EXISTS slots (
  slot_id   INT AUTO_INCREMENT PRIMARY KEY,
  slot_no   VARCHAR(20) NOT NULL UNIQUE,
  slot_type VARCHAR(2)  NOT NULL CHECK (slot_type IN ('2W', '4W')),
  level     VARCHAR(10) NOT NULL,
  is_free   TINYINT(1)  NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rates (
  slot_type  VARCHAR(2) PRIMARY KEY CHECK (slot_type IN ('2W', '4W')),
  first_hour DECIMAL(8,2) NOT NULL,
  extra_hour DECIMAL(8,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicles (
  vehicle_no   VARCHAR(15) PRIMARY KEY,
  vehicle_type VARCHAR(2) NOT NULL CHECK (vehicle_type IN ('2W', '4W'))
);

CREATE TABLE IF NOT EXISTS tickets (
  ticket_id  INT AUTO_INCREMENT PRIMARY KEY,
  vehicle_no VARCHAR(15) NOT NULL,
  slot_id    INT NOT NULL,
  issued_by  INT NOT NULL,
  entry_time DATETIME NOT NULL,
  exit_time  DATETIME NULL,
  status     VARCHAR(6) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
  FOREIGN KEY (vehicle_no) REFERENCES vehicles(vehicle_no),
  FOREIGN KEY (slot_id)    REFERENCES slots(slot_id),
  FOREIGN KEY (issued_by)  REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS bills (
  bill_id   INT AUTO_INCREMENT PRIMARY KEY,
  ticket_id INT NOT NULL UNIQUE,
  hours     INT NOT NULL,
  amount    DECIMAL(8,2) NOT NULL,
  paid_time DATETIME NOT NULL,
  FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
);
