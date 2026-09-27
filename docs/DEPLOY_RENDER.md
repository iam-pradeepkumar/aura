# Deploy AURA Command Center on Render

Host the **SAR Command Center** dashboard on [Render](https://render.com). Every push to `main` triggers an automatic redeploy when the service is linked to your GitHub repo.

---

## What runs on Render

| Feature | Cloud | Notes |
|---------|-------|-------|
| Command map + 3D units | Yes | MapLibre + Three.js in browser |
| Mark disaster zone | Yes | Draw polygon on satellite map |
| Place survivors (sim) | Yes | Click to seed victim positions |
| Start mission | Yes | Spiderbots + drones patrol in simulation |
| WiFi CSI homing + FOUND pins | Yes | Built-in kinematic sim engine |
| WebSocket telemetry | Yes | `/ws/command` |
| Live ESP32 hardware | **No** | Run `tools/field_live.py` locally |
| Gazebo / Isaac Sim | **No** | Local ROS 2 stack only |

---

## One-time setup (GitHub already connected)

### Option A — Blueprint (recommended)

1. Push this repo to GitHub:
   ```bash
   git push origin main
   ```

2. [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint**.

3. Select your GitHub repo → Render reads `render.yaml` → **Apply**.

4. Wait for the first build (~2–4 min).

5. Open your service URL, e.g. `https://aura-command-center.onrender.com`.

### Option B — Manual Web Service

| Field | Value |
|-------|-------|
| **Runtime** | Python 3 |
| **Branch** | `main` |
| **Build Command** | `pip install --upgrade pip && pip install -r requirements.txt` |
| **Start Command** | `uvicorn dashboard.app:app --host 0.0.0.0 --port $PORT` |
| **Health Check** | `/api/health` |
| **Auto-Deploy** | On (default when linked to GitHub) |

**Environment variables:**

| Key | Value |
|-----|-------|
| `PYTHON_VERSION` | `3.12.3` |
| `PYTHONUNBUFFERED` | `1` |

---

## Auto-deploy on push

Once the Render service is connected to GitHub:

1. Commit and push to `main`.
2. Render detects the push and starts a new build automatically.
3. When the build succeeds, traffic switches to the new version.

To deploy manually: Render Dashboard → your service → **Manual Deploy** → **Deploy latest commit**.

---

## Verify after deploy

```bash
curl https://YOUR-SERVICE.onrender.com/api/health
```

Expected:

```json
{"status":"ok","service":"aura-command-center","version":"4.0.0","mode":"sar-command"}
```

Open `https://YOUR-SERVICE.onrender.com/` — you should see the full-screen command map.

**Quick demo flow:**

1. Search an address → **Locate**
2. **Mark disaster zone** → click corners → **Close polygon**
3. **Place survivors** → click inside the zone
4. **Start mission** → watch spiderbots/drones patrol and mark FOUND pins

---

## Free tier notes

- **Spin-down** — service sleeps after ~15 min idle; first visit may take 30–60 s to wake.
- **750 hours/month** — one free web service is enough for demos.
- Upgrade to **Starter** for always-on and faster cold starts.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Build fails on `scipy` | Ensure `PYTHON_VERSION` is `3.12.3`; build uses `pip install --upgrade pip` |
| 502 on first load | Free tier waking up — wait 60 s and refresh |
| WebSocket disconnects | Render supports WebSockets on web services; check browser console |
| Port error | Start command must use `$PORT`, not a fixed port |
| Map tiles blank | Outbound HTTPS must be allowed (Esri satellite tiles) |

**Logs:** Render Dashboard → service → **Logs**.

---

## Local vs Render

| | Local `python3 dashboard/run.py` | Render |
|--|----------------------------------|--------|
| URL | `http://127.0.0.1:8847` | `https://….onrender.com` |
| Simulation mission | Yes | Yes |
| Live ESP32 CSI | Yes (with hotspot) | No |
| Gazebo ROS 2 | Yes (local) | No |

For hackathons: share the Render URL for the SAR command demo; use a laptop for live hardware or Gazebo.
