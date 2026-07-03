# Deploy to Render

Click the button below to deploy instantly:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Vimochini/Contraste)

## Manual Deployment

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New +** → **Static Site**
3. Connect GitHub: Select `Vimochini/Contraste`
4. Settings:
   - Name: `universal-api-client`
   - Build Command: (leave empty)
   - Publish Directory: `.`
5. Click **Deploy**

Your live site will be at: `https://universal-api-client.onrender.com/universal-api-client.html`

## After Deployment

1. Open the live URL
2. Update API endpoint in the app (line 702)
3. Replace placeholder with your actual API URL
4. Test by entering a website URL
