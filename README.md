# FRAS - Face Recognition Attendance System

A web-based attendance system that marks students present by recognizing their faces through a webcam. Built with Flask, MySQL and the `face_recognition` library.

## Team

- [konokuzzaman](https://github.com/konokuzzaman)
- [wahiPP](https://github.com/wahiPP)

## Features

- **Admin and faculty login**, each with their own dashboard
- **Manage** departments, faculty, students, courses, sections and enrollments
- **Capture student faces** to register them for recognition
- **Live attendance**: start a session, and recognized students are marked present automatically from the webcam
- **Unknown faces** are saved for review
- **Manual attendance** corrections, with an audit log
- **Export** attendance records as CSV

## Tech Stack

- Python, Flask
- MySQL
- face_recognition (dlib), NumPy
- HTML, CSS, JavaScript, Bootstrap

## How to Run

1. Install the dependencies (dlib needs CMake and a C++ compiler on Windows):
   ```
   pip install -r requirements.txt
   ```
2. Create the database and tables:
   ```
   mysql -u root -p < schema.sql
   ```
3. Create a `.env` file in the project folder with your MySQL login:
   ```
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   ```
4. Start the app:
   ```
   python app.py
   ```
5. Open http://127.0.0.1:5000 in your browser.
