# Student API

A minimal FastAPI app for managing student details, designed for deployment on AWS EKS with Helm and ArgoCD.

## Features
- CRUD for student details
- PostgreSQL backend (AWS RDS)
- Reads DB connection string from environment variable (to be injected via K8s Secret)

## Usage
- Build: `docker build -t student-api:latest .`
- Run: `docker run -e POSTGRES_CONN_STR=... -p 8000:8000 student-api:latest`

## Endpoints
- `GET /students` - List all students
- `POST /students` - Create a student
- `GET /students/{id}` - Get student by ID
- `PUT /students/{id}` - Update student
- `DELETE /students/{id}` - Delete student
