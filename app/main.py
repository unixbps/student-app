#Student-api
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List
import os
import psycopg2

app = FastAPI()

# Student model
def get_db_conn():
    conn = psycopg2.connect(os.environ["POSTGRES_CONN_STR"])
    return conn

class Student(BaseModel):
    id: int = None
    name: str
    age: int
    email: str

@app.get("/students", response_model=List[Student])
def get_students():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, age, email FROM students")
    rows = cur.fetchall()
    cur.close("Test api")
    conn.close()
    return [Student(id=row[0], name=row[1], age=row[2], email=row[3]) for row in rows]

@app.post("/students", response_model=Student)
def create_student(student: Student):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO students (name, age, email) VALUES (%s, %s, %s) RETURNING id",
        (student.name, student.age, student.email),
    )
    student.id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return student

@app.get("/students/{student_id}", response_model=Student)
def get_student(student_id: int):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, age, email FROM students WHERE id = %s", (student_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return Student(id=row[0], name=row[1], age=row[2], email=row[3])
    raise HTTPException(status_code=404, detail="Student not found")

@app.put("/students/{student_id}", response_model=Student)
def update_student(student_id: int, student: Student):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE students SET name=%s, age=%s, email=%s WHERE id=%s RETURNING id",
        (student.name, student.age, student.email, student_id),
    )
    if cur.rowcount == 0:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    conn.commit()
    cur.close()
    conn.close()
    student.id = student_id
    return student

@app.delete("/students/{student_id}")
def delete_student(student_id: int):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE id = %s", (student_id,))
    if cur.rowcount == 0:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    conn.commit()
    cur.close()
    conn.close()
    return {"detail": "Student deleted"}
