-- Run this in your MySQL instance
CREATE DATABASE IF NOT EXISTS fras_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE fras_db;

CREATE TABLE admin_account (
  admin_id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL UNIQUE,
  display_name VARCHAR(150),
  email VARCHAR(150),
  phone VARCHAR(50),
  avatar_url VARCHAR(300),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE department (
  department_id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(20) NOT NULL UNIQUE,
  name VARCHAR(150) NOT NULL,
  chair_name VARCHAR(150),
  contact_email VARCHAR(150),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE faculty (
  faculty_id INT AUTO_INCREMENT PRIMARY KEY,
  faculty_code VARCHAR(50) NOT NULL UNIQUE,
  full_name VARCHAR(200) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  phone VARCHAR(50),
  department_id INT,
  password_hash VARCHAR(255) NOT NULL,
  avatar_path VARCHAR(500),
  status ENUM('active','inactive') DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (department_id) REFERENCES department(department_id) ON DELETE SET NULL
);

CREATE TABLE student (
  student_id INT AUTO_INCREMENT PRIMARY KEY,
  roll VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(200) NOT NULL,
  department_id INT,
  batch VARCHAR(50),
  email VARCHAR(150),
  phone VARCHAR(30),
  photo_path VARCHAR(500),
  status ENUM('active','inactive') DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (department_id) REFERENCES department(department_id) ON DELETE SET NULL
);

CREATE TABLE course (
  course_id INT AUTO_INCREMENT PRIMARY KEY,
  course_code VARCHAR(50) NOT NULL UNIQUE,
  course_name VARCHAR(200) NOT NULL,
  department_id INT,
  credit DECIMAL(3,1) DEFAULT 3.0,
  description TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (department_id) REFERENCES department(department_id) ON DELETE SET NULL
);

CREATE TABLE section (
  section_id INT AUTO_INCREMENT PRIMARY KEY,
  course_id INT NOT NULL,
  section_no VARCHAR(10),
  semester VARCHAR(20),
  academic_year VARCHAR(9),
  faculty_id INT,
  schedule_info VARCHAR(255),
  FOREIGN KEY (course_id) REFERENCES course(course_id) ON DELETE CASCADE,
  FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL
);

CREATE TABLE faculty_assignment (
  assignment_id INT AUTO_INCREMENT PRIMARY KEY,
  faculty_id INT NOT NULL,
  section_id INT NOT NULL,
  role ENUM('primary','assistant') DEFAULT 'primary',
  assigned_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_assignment (faculty_id, section_id),
  FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE,
  FOREIGN KEY (section_id) REFERENCES section(section_id) ON DELETE CASCADE
);

CREATE TABLE enrollment (
  enrollment_id INT AUTO_INCREMENT PRIMARY KEY,
  student_id INT NOT NULL,
  section_id INT NOT NULL,
  enrolled_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_enroll (student_id, section_id),
  FOREIGN KEY (student_id) REFERENCES student(student_id) ON DELETE CASCADE,
  FOREIGN KEY (section_id) REFERENCES section(section_id) ON DELETE CASCADE
);

CREATE TABLE attendance_session (
  session_id INT AUTO_INCREMENT PRIMARY KEY,
  section_id INT NOT NULL,
  faculty_id INT,
  mode ENUM('smart','manual') DEFAULT 'smart',
  session_started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  session_closed_at TIMESTAMP NULL,
  status ENUM('open','closed') DEFAULT 'open',
  device_name VARCHAR(150),
  FOREIGN KEY (section_id) REFERENCES section(section_id) ON DELETE CASCADE,
  FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL
);

CREATE TABLE attendance_record (
  attendance_id INT AUTO_INCREMENT PRIMARY KEY,
  enrollment_id INT NOT NULL,
  session_id INT,
  attendance_date DATE NOT NULL,
  status ENUM('present','absent','late','excused') DEFAULT 'present',
  time_in TIME,
  time_out TIME,
  marked_by_faculty INT,
  mode ENUM('smart','manual') DEFAULT 'smart',
  note VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_attendance (enrollment_id, attendance_date),
  FOREIGN KEY (enrollment_id) REFERENCES enrollment(enrollment_id) ON DELETE CASCADE,
  FOREIGN KEY (session_id) REFERENCES attendance_session(session_id) ON DELETE SET NULL,
  FOREIGN KEY (marked_by_faculty) REFERENCES faculty(faculty_id) ON DELETE SET NULL
);

CREATE TABLE manual_attendance_audit (
  audit_id INT AUTO_INCREMENT PRIMARY KEY,
  attendance_id INT NOT NULL,
  updated_by INT,
  previous_status ENUM('present','absent','late','excused'),
  new_status ENUM('present','absent','late','excused'),
  remarks VARCHAR(255),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (attendance_id) REFERENCES attendance_record(attendance_id) ON DELETE CASCADE,
  FOREIGN KEY (updated_by) REFERENCES faculty(faculty_id) ON DELETE SET NULL
);

CREATE TABLE face_data (
  face_id INT AUTO_INCREMENT PRIMARY KEY,
  student_id INT NOT NULL,
  storage_path VARCHAR(500) NOT NULL,
  capture_source ENUM('webcam','upload') DEFAULT 'webcam',
  captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (student_id) REFERENCES student(student_id) ON DELETE CASCADE
);

CREATE TABLE unknown_faces (
  unknown_id INT AUTO_INCREMENT PRIMARY KEY,
  capture_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  storage_path VARCHAR(500) NOT NULL,
  session_id INT,
  tag VARCHAR(200),
  FOREIGN KEY (session_id) REFERENCES attendance_session(session_id) ON DELETE SET NULL
);

CREATE TABLE system_log (
  log_id INT AUTO_INCREMENT PRIMARY KEY,
  action_type VARCHAR(100),
  actor VARCHAR(150),
  details TEXT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE device_info (
  device_id INT AUTO_INCREMENT PRIMARY KEY,
  device_name VARCHAR(200),
  ip_address VARCHAR(100),
  camera_index INT DEFAULT 0,
  status ENUM('active','inactive') DEFAULT 'active',
  last_seen TIMESTAMP NULL
);

CREATE TABLE session_log (
  session_id INT AUTO_INCREMENT PRIMARY KEY,
  admin_id INT,
  faculty_id INT,
  login_time TIMESTAMP,
  logout_time TIMESTAMP,
  ip_address VARCHAR(100),
  FOREIGN KEY (admin_id) REFERENCES admin_account(admin_id) ON DELETE SET NULL,
  FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL
);

CREATE INDEX idx_face_student ON face_data(student_id);
CREATE INDEX idx_unknown_time ON unknown_faces(capture_time);
CREATE INDEX idx_attendance_date ON attendance_record(attendance_date);