# Telegramtorrent bot

It is the telegram bot whuch can download files with BitTorrent protocol


# Running

Generate your `api_id` and `api_hash` ([instruction](https://core.telegram.org/api/obtaining_api_id))

Add user's ID to white list — array `allowed_users` in `main.py` (line 26)

Then use this commands:

```
pip3 install -r requirements.txt
API_ID=<you API ID> API_HASH=<YOUR_API_HASH> python3 main.py
```

This bot looks like a telegram user. Because regular bots can upload only files below 50 MB ([Bots FAQ](https://core.telegram.org/bots/faq))

Then you have to enter your mobile phone, 2FA code and application will create a file `firstsession.session` with telegram tokens

# Using

If you want to download contents of `.torrent` file, you have to send this file to the user which was logged in with this application

After uploading, you can download zip archive with necessary files

# FAQ

## Bot separated zip archive. What is the way to make single file?

Use this command:
`cat filename.zip_* > filename.zip`

