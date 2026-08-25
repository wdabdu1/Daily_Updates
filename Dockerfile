# Multi-stage build: compile the React frontend, then serve it from the
# FastAPI backend as a single Railway service (same simplicity as the old
# single Streamlit process).

FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS backend
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# The built frontend lands where main.py expects it: backend/static
COPY --from=frontend-build /frontend/dist ./static

EXPOSE 8501
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8501"]
