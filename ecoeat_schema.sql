CREATE DATABASE ecoeat;
USE ecoeat;

-- =========================
-- 1. STUDENTS TABLE
-- =========================
CREATE TABLE Students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    eco_points INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- 2. VENDORS TABLE
-- =========================
CREATE TABLE Vendors (
    vendor_id INT AUTO_INCREMENT PRIMARY KEY,
    vendor_name VARCHAR(100) NOT NULL,
    location VARCHAR(100),
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

-- =========================
-- 3. ADMINS TABLE
-- =========================
CREATE TABLE Admins (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

-- =========================
-- 4. SURPRISE BOXES TABLE
-- =========================
CREATE TABLE Surprise_Boxes (
    box_id INT AUTO_INCREMENT PRIMARY KEY,
    vendor_id INT NOT NULL,
    title VARCHAR(100) NOT NULL,
    description TEXT,
    original_price DECIMAL(10,2) NOT NULL,
    discounted_price DECIMAL(10,2) NOT NULL,
    quantity_available INT NOT NULL,
    pickup_start DATETIME NOT NULL,
    pickup_end DATETIME NOT NULL,
    eco_points_reward INT DEFAULT 10,
    status VARCHAR(20) DEFAULT 'Available',

    FOREIGN KEY (vendor_id)
    REFERENCES Vendors(vendor_id)
    ON DELETE CASCADE
);

-- =========================
-- 5. ORDERS TABLE
-- =========================
CREATE TABLE Orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    box_id INT NOT NULL,
    quantity INT DEFAULT 1,
    total_price DECIMAL(10,2) NOT NULL,
    order_status VARCHAR(20) DEFAULT 'Reserved',
    pickup_code VARCHAR(6) UNIQUE DEFAULT NULL,
    order_date DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (student_id)
    REFERENCES Students(student_id)
    ON DELETE CASCADE,

    FOREIGN KEY (box_id)
    REFERENCES Surprise_Boxes(box_id)
    ON DELETE CASCADE
);

-- =========================
-- 6. ECO POINT LOG TABLE
-- =========================
CREATE TABLE Eco_Point_Log (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    points_earned INT NOT NULL,
    reason VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (student_id)
    REFERENCES Students(student_id)
    ON DELETE CASCADE
);
