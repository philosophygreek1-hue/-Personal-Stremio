# 📁 Personal Stremio Addon

A Stremio addon to stream your **personal files** from a Telegram channel — no TMDB, no IMDb. Just your own files, organized into folders.

## How It Works

1. You upload files to your Telegram channel
2. The bot picks them up and indexes them
3. Browse and stream from Stremio under **"MyFiles"**

## Folder Organization

Files are organized into folders. To assign a file to a folder, add a caption tag:

```
folder:Education
folder:Music
folder:WorkDocs
```

If no folder tag is given, files go to the **General** folder (or whatever you set `DEFAULT_FOLDER` to in Railway).

## Railway Environment Variables

| Variable | Description |
|---|---|
| `API_ID` | From https://my.telegram.org |
| `API_HASH` | From https://my.telegram.org |
| `BOT_TOKEN` | Your main bot token |
| `HELPER_BOT_TOKEN` | Second bot for streaming |
| `OWNER_ID` | Your Telegram user ID |
| `AUTH_CHANNEL` | Your channel ID (e.g. `-1004480414116`) |
| `DATABASE` | Two MongoDB URIs separated by comma |
| `BASE_URL` | Your Railway public URL |
| `PORT` | `8000` |
| `ADMIN_USERNAME` | Admin panel login |
| `ADMIN_PASSWORD` | Admin panel password |
| `DEFAULT_FOLDER` | Default folder name (default: `General`) |

## Deploy to Railway

1. Push this repo to GitHub
2. Connect to Railway → New Project → Deploy from GitHub
3. Add all environment variables from above
4. Set `BASE_URL` to your Railway domain after first deploy → redeploy

## Supported File Types

- Videos (mp4, mkv, avi, etc.)
- Documents (pdf, docx, zip, etc.)
- Audio (mp3, flac, etc.)

## Credits

Based on [Telegram-Stremio](https://github.com/weebzone/Telegram-Stremio) by weebzone.
Modified for personal file streaming without TMDB/IMDb dependency.
