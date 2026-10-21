FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -r requirements.txt
COPY app.py timeline.py reliability.py ai_queue.py subtitle_files.py subtitle_quality.py external_providers.py subtitle_optimizer.py subtitle_google.py ai_provider_settings.py workflow_plan.py ./
RUN python -c "import external_providers, subtitle_optimizer, subtitle_google, ai_provider_settings, workflow_plan; print('Subtitle modules OK')"
ENV PYTHONUNBUFFERED=1
EXPOSE 8765
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8765"]
