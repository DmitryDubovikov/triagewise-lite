# Control-plane dashboard image (iter 7). Pinned base + pinned deps (requirements.txt is this
# image's lock, analog of uv.lock). App code is NOT baked in: compose mounts ./app read-only,
# so the panel always renders the working tree without a rebuild. Streamlit telemetry off —
# same hygiene posture as promptfoo/prefect.
FROM python:3.12.13-slim

# PYTHONPATH: streamlit is a console script — it puts the script's own dir (/srv/app/ui) on
# sys.path, never the cwd, so the mounted `app` package needs /srv spelled out explicitly.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8501
CMD ["streamlit", "run", "app/ui/dashboard.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
