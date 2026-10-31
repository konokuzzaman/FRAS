# face_utils.py
import os
import face_recognition
import numpy as np
from config import DB_CONFIG, FACE_MATCH_TOLERANCE
from mysql.connector import connect

class FaceDBCache:
    def __init__(self):
        self.known_encodings = []
        self.known_student_ids = []

    def load_from_db(self):
        self.known_encodings = []
        self.known_student_ids = []
        try:
            conn = connect(**DB_CONFIG)
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT face_id, student_id, storage_path FROM face_data WHERE storage_path IS NOT NULL")
            rows = cur.fetchall()
            for r in rows:
                p = r['storage_path']
                if p and os.path.exists(p):
                    try:
                        img = face_recognition.load_image_file(p)
                        encs = face_recognition.face_encodings(img)
                        if encs:
                            self.known_encodings.append(encs[0])
                            self.known_student_ids.append(r['student_id'])
                    except Exception as e:
                        print("face_utils: error encoding", p, e)
            cur.close()
            conn.close()
        except Exception as e:
            print("face_utils load_from_db error:", e)

    def find_match(self, unknown_encoding, tolerance=FACE_MATCH_TOLERANCE):
        if not self.known_encodings:
            return None
        distances = face_recognition.face_distance(self.known_encodings, unknown_encoding)
        min_idx = np.argmin(distances)
        if distances[min_idx] <= tolerance:
            return self.known_student_ids[min_idx], float(distances[min_idx])
        return None

face_cache = FaceDBCache()