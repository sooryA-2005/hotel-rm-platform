# Hotel Revenue Management & Dynamic Pricing Platform

A working Streamlit implementation of the pipeline described in the Day 1 design doc:

```
Ingest → Store → Forecast → Optimize (+ guardrails) → Explain → Publish (dashboard)
```

Live demo dashboard with four views: a **rate calendar**, a **what-if price simulator**,
a **static-vs-dynamic RevPAR comparison**, and a **forecast / model internals** tab.

> All data is **synthetically generated** (`src/data_gen.py`) — real hotel booking data
> is proprietary, so this stands in for a PMS feed, per the Day 1 Assumptions & Constraints.

## Project structure

```
hotel-rm-platform/
├── app.py                  # Streamlit dashboard (4 tabs)
├── src/
│   ├── data_gen.py         # Synthetic PMS/booking data generator (Data Ingestion & Feature Store)
│   ├── forecast.py         # Demand Forecast Model (gradient boosting, with rule-based fallback)
│   └── pricing_engine.py   # Price Optimization Engine + Explainability Layer, with guardrails
├── .streamlit/config.toml  # Theme
├── requirements.txt
└── README.md
```

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Deploy — GitHub + Streamlit Community Cloud (free hosting)

**1. Push this project to a new GitHub repo**

```bash
cd hotel-rm-platform
git init                                   # skip if already a git repo
git add .
git commit -m "Initial commit: Hotel RM & Dynamic Pricing Platform"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

(Create the empty repo first at github.com/new — don't initialize it with a README,
so the push above doesn't conflict.)

**2. Deploy on Streamlit Community Cloud**

1. Go to **https://share.streamlit.io** and sign in with your GitHub account.
2. Click **"New app"**.
3. Pick your repository, branch (`main`), and set **Main file path** to `app.py`.
4. Click **Deploy**. Streamlit Cloud installs `requirements.txt` automatically and
   builds the app — first deploy typically takes 1-3 minutes.
5. You'll get a public URL like `https://<your-app-name>.streamlit.app`.

**Updating the live app:** any `git push` to `main` triggers an automatic redeploy —
no extra steps needed.

### Alternative: GitHub Actions → self-hosted / container deploy

If you'd rather deploy to your own infrastructure (e.g., a VM, Render, Fly.io, or a
container registry) instead of Streamlit Community Cloud, a minimal Dockerfile is enough
to containerize this app:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
```

Then a simple GitHub Actions workflow (`.github/workflows/deploy.yml`) can build and
push the image to your target host on every push to `main`. Ask if you'd like this
workflow file scaffolded — it's not included by default since it depends on which
host/registry you're deploying to.

## Design references

This implementation follows the architecture, data model, and guardrails specified in:
- `Hotel_RM_Dynamic_Pricing_Technical_Analysis.docx` — literature review, algorithms, simulations
- `Day1_Planning_Design_Hotel_RM_Platform.docx` — SRS, SOP, technical design, DB & API design

Key guardrails enforced in `src/pricing_engine.py` (independent of the UI):
- Price multiplier bounded to **0.75×–1.70×** of base rate
- Maximum **12%** day-over-day price change
- Every recommendation carries a human-readable reason code
