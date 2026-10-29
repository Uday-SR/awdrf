# React front-end
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Python API + static files
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/tests ./tests
COPY backend/fetch_data.py ./fetch_data.py
COPY --from=frontend /fe/dist ./static

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
