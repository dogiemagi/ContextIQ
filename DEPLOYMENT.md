# ContextIQ Deployment Guide

## Overview

This guide covers deploying ContextIQ to **Render** (recommended for free tier) and other platforms.

---

## 🚀 Quick Deploy to Render (Recommended)

### 1. Prerequisites
- GitHub account with this repo
- [Render.com](https://render.com) account (free tier)
- [Groq API key](https://console.groq.com)

### 2. Deploy in 3 Steps

#### Step 1: Connect Repository
1. Visit [Render Dashboard](https://dashboard.render.com)
2. Click **New** → **Web Service**
3. Select **GitHub** and authorize Render
4. Choose `dogiemagi/ContextIQ` repository
5. Select the branch you want to deploy

#### Step 2: Configure Service
- **Name**: `contextiq` (or your preferred name)
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app`
- **Instance Type**: Free tier (`$0/month`)

#### Step 3: Set Environment Variables
1. Go to **Environment** tab
2. Add variable:
   ```
   Key: GROQ_API_KEY
   Value: sk-proj-xxxxxxxxxxxxx
   ```
   (Get this from [console.groq.com](https://console.groq.com))

3. Click **Deploy** 🎉

### 3. Verify Deployment
Once deployment completes:
- Visit `https://<your-service-name>.onrender.com`
- Check health: `https://<your-service-name>.onrender.com/health`
- Expected response: `{"status": "healthy", "service": "ContextIQ"}`

---

## 📋 Required Files for Deployment

The following files are essential for Render deployment:

| File | Purpose |
|------|---------|
| `Procfile` | Specifies how to start the app (Gunicorn command) |
| `requirements.txt` | Python dependencies with versions |
| `runtime.txt` | Python version (3.11.0) |
| `render.yaml` | Render-specific configuration (optional) |
| `.env.example` | Template for environment variables |
| `.gitignore` | Excludes uploads and sensitive files |
| `app.py` | Main Flask app (updated with logging & health check) |

All required files are included in this repo ✅

---

## ⚠️ Important Considerations

### File Storage (Critical!)
**Problem**: Uploaded files are stored in `/uploads`, which is **ephemeral** (temporary).
- Files **will be deleted** when the service restarts
- Free tier restarts after 15 minutes of inactivity
- Persistent storage costs extra

**Solutions**:
1. **For Development**: Accept ephemeral storage (current setup)
2. **For Production**: Use Render Persistent Disks or S3:
   ```bash
   # Add to requirements.txt
   boto3>=1.26.0  # for S3
   ```
   Then modify upload handler to use S3

### Vector Database (ChromaDB)
- ChromaDB vectors are stored in memory
- Vectors reset when service restarts
- Users must re-upload documents after restart
- For persistence, integrate with external vector DB (Pinecone, Supabase)

### API Rate Limits
- Groq API has rate limits on free tier
- Monitor usage in [Groq Console](https://console.groq.com)
- Consider switching to paid tier for production

---

## 🔧 Local Development

### Setup
```bash
# Clone repository
git clone https://github.com/dogiemagi/ContextIQ.git
cd ContextIQ

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### Run Locally
```bash
# Development mode
python app.py

# Production simulation (like Render)
gunicorn app:app --bind 0.0.0.0:8000
```

Visit `http://localhost:5000` (Flask) or `http://localhost:8000` (Gunicorn)

---

## 🔐 Security Best Practices

### Environment Variables
✅ DO:
- Store API keys in Render Environment tab
- Use `.env.example` as template (no real keys)
- Never commit `.env` file (in `.gitignore`)

❌ DON'T:
- Hardcode API keys in code
- Commit sensitive files
- Share `.env` file

### API Key Rotation
Rotate Groq API key annually:
1. Generate new key in [Groq Console](https://console.groq.com)
2. Update in Render dashboard
3. Test immediately
4. Delete old key

---

## 🚨 Troubleshooting

### Issue: "GROQ_API_KEY not set"
**Cause**: Environment variable not configured
**Fix**:
1. Go to Render dashboard
2. Select your service
3. Check **Environment** tab
4. Add/verify `GROQ_API_KEY`
5. Manually trigger redeploy

### Issue: 502 Bad Gateway
**Cause**: Gunicorn process crashed
**Fix**:
1. Check **Logs** tab for error messages
2. Verify `requirements.txt` compatible with Python 3.11
3. Ensure `GROQ_API_KEY` is set
4. Restart service from dashboard

### Issue: Service starts but no response
**Cause**: App crashed during initialization
**Fix**:
```bash
# Test locally first
python app.py

# Check logs for specific errors
# Look for "ERROR" messages in Render logs
```

### Issue: Slow uploads (>30 seconds)
**Cause**: Large file or slow embedding model
**Fix**:
- Split large files before uploading
- Use free tier only for testing
- Consider upgrading instance type

### Issue: "Page not found" after upload
**Cause**: Session lost (service restarted)
**Fix**: Re-upload file (this is expected behavior on free tier)

---

## 📊 Monitoring & Logs

### View Logs in Render
1. Go to service dashboard
2. Click **Logs** tab
3. Select time range
4. Search for "ERROR" or "WARNING"

### Key Log Messages
```
✅ INFO - Groq client initialized successfully     # Good
✅ INFO - Starting ContextIQ server on port 10000  # Good
❌ ERROR - GROQ_API_KEY environment variable...    # Missing API key
❌ ERROR - Failed to initialize Groq client        # Invalid API key
```

---

## 🎯 Next Steps

### For Development
- Test locally with test documents
- Verify API responses
- Try edge cases (large files, special characters)

### For Production
1. **Use Persistent Storage**: Switch to S3 or Render Persistent Disks
2. **Add Database**: PostgreSQL for sessions and document metadata
3. **Implement Auth**: User authentication and API keys
4. **Add Monitoring**: Error tracking (Sentry), logging (LogRocket)
5. **Set Up CI/CD**: Auto-deploy on git push
6. **Custom Domain**: Add domain in Render settings

---

## 📚 Resources

- [Render Documentation](https://render.com/docs)
- [Flask Deployment Guide](https://flask.palletsprojects.com/deployment/)
- [Groq API Docs](https://console.groq.com/docs)
- [LangChain Documentation](https://python.langchain.com/)
- [ChromaDB Persistence](https://docs.trychroma.com/)

---

## 💬 Support

For issues or questions:
1. Check Render logs first
2. Review troubleshooting section above
3. Check Groq console for API status
4. Create GitHub issue in repository

---

**Last Updated**: 2025
**Status**: Production-ready for testing and development
