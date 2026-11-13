FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=5000
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m defect_analysis.train_model && useradd --create-home app && chown -R app /app
USER app
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/api/health')"
CMD ["sh", "-c", "gunicorn --preload --workers 2 --timeout 120 --bind 0.0.0.0:$PORT 'backend.app:create_app()'"]
