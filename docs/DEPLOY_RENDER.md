# Deploy AURA on Render

Host the **AURA web dashboard** (home, simulation, alerts, DM console) on [Render](https://render.com) as a Python web service.

---

## What works on Render

| Feature | Cloud | Notes |
|---------|-------|-------|
| Home page | Yes | Full hand-drawn UI |
| **Try simulation** (`act_105_48`) | Yes | Bundled in `dashboard/demo_data/` |
| Custom WiMANS upload | Yes* | *Files are ephemeral — lost on redeploy |
| DM Console (simulate alert) | Yes | Best way to demo alerts without USGS |
| USGS / Open-Meteo polling | Yes | If Render outbound network is up |
| Public `/alerts` feed | Yes | |
| WebSocket updates | Yes | |
| Live ESP32 (`field_live.py`) | **No** | Needs local UDP + `AURA_HUB` hotspot |
| LAN multicast alerts | **No** | Cloud cannot reach your local LAN |

---

## Prerequisites

1. **GitHub repository** with your AURA code pushed (see sync note below if you use Cursor cloud).
2. **Render account** — [render.com](https://render.com) (free tier works for demos).
3. Repo must include `dashboard/demo_data/act_105_48.{mp4,mat,npy}` (~6 MB) — already in this project.

---

## Option A — Blueprint (fastest)

This repo includes `render.yaml`. Render can create the service automatically.

1. Push code to GitHub:
   ```bash
   git push origin main
   ```

2. Open [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint**.

3. Connect your GitHub account and select the **aura** repository.

4. Render detects `render.yaml` → click **Apply**.

5. Wait for build (~3–8 min first time; installs numpy, scipy, opencv-headless).

6. Open the URL Render gives you, e.g. `https://aura-dashboard.onrender.com`.

---

## Option B — Manual Web Service

1. **Render Dashboard** → **New** → **Web Service**.

2. Connect GitHub → select your **aura** repo.

3. Settings:

   | Field | Value |
   |-------|-------|
   | **Name** | `aura-dashboard` |
   | **Region** | Singapore (closest to India) or Oregon |
   | **Branch** | `main` |
   | **Runtime** | Python 3 |
   | **Build Command** | `pip install --upgrade pip && pip install -r requirements.txt` |
   | **Start Command** | `uvicorn dashboard.app:app --host 0.0.0.0 --port $PORT` |
   | **Plan** | Free (or Starter for always-on) |

4. **Environment** → add:

   | Key | Value |
   |-----|-------|
   | `PYTHON_VERSION` | `3.12.3` |
   | `MPLBACKEND` | `Agg` |
   | `PYTHONUNBUFFERED` | `1` |

5. **Health Check Path** (optional): `/api/version`

6. Click **Create Web Service**.

---

## Verify after deploy

1. **Health check**
   ```bash
   curl https://YOUR-SERVICE.onrender.com/api/version
   ```
   Expected: `{"processor_version":"2026.09.04-42","mode":"csi-only"}`

2. **Pages**
   - `https://YOUR-SERVICE.onrender.com/` — home
   - `https://YOUR-SERVICE.onrender.com/simulation` — click **Try simulation**
   - `https://YOUR-SERVICE.onrender.com/manage` — simulate hazard → broadcast
   - `https://YOUR-SERVICE.onrender.com/alerts` — public feed

3. **Simulation** — first run may take 10–20 s (cold start + CSI processing).

4. **Alerts offline?** — On free tier, if USGS fails, uncheck **Live API polling** on Alerts and use **DM Console → Simulate hazard**.

---

## Sync code from Cursor cloud to GitHub

If `git pull` on your laptop shows “already up to date” but Cursor has newer commits:

```bash
git remote add aura-cloud https://origin.cursor.com/git/pradeep-kumar-s/tmp-2f8f2732c0c42b4f.git
git fetch aura-cloud main
git merge aura-cloud/main
git push origin main
```

Then trigger **Manual Deploy** on Render (or wait for auto-deploy on push).

---

## Free tier notes

- **Spin-down** — service sleeps after ~15 min idle; first visit takes 30–60 s to wake.
- **Ephemeral disk** — uploaded simulation files and `alert_settings.json` reset on redeploy. Bundled `act_105_48` demo always works.
- **750 hours/month** — enough for one always-on demo service if you stay on free plan limits.

Upgrade to **Starter** ($7/mo) for always-on and faster cold starts.

---

## Optional: webhook for Slack

After deploy:

1. Open `https://YOUR-SERVICE.onrender.com/manage`
2. Paste Slack incoming webhook URL
3. Simulate → approve → broadcast — webhook fires on approve

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Build fails on `opencv` | Ensure root `requirements.txt` uses `opencv-python-headless` |
| Build fails on `mat73` | Python 3.12 + `pip install --upgrade pip` before install |
| Simulation 400 error | Check Render logs; confirm `demo_data/` files exist in repo |
| USGS “offline” | Normal without DNS; use DM simulate or enable Live polling when online |
| 502 on first load | Free tier waking up — wait 60 s and refresh |
| Port error | Start command must use `$PORT`, not `8847` |

**Logs:** Render Dashboard → your service → **Logs** tab.

---

## Custom domain (optional)

Render Dashboard → service → **Settings** → **Custom Domains** → add your domain and follow DNS instructions.

---

## Local vs Render

| | Local `python3 dashboard/run.py` | Render |
|--|----------------------------------|--------|
| Port | `8847` | Render `$PORT` (HTTPS URL) |
| ESP32 live sensing | Yes | No |
| Try simulation | Yes | Yes |
| DM alert demo | Yes | Yes |

For hackathons/judges: share the Render URL for simulation + alert demo; use laptop + ESP32 only for live CSI hardware demo.
