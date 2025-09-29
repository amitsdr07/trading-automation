# Daily Markets Email via GitHub Actions + Resend

This project:
- Runs daily on schedule (08:30 IST = 03:00 UTC)
- Calls OpenAI to generate:
  1. India & Global stock market news
  2. GIFT Nifty sentiment
  3. Nifty 50 stocks down ≥20% this month
- Sends **one email** with all 3 sections included via Resend

## Setup

1. Create a free [Resend](https://resend.com) account, verify a sender domain/email.
2. In GitHub repo → Settings → Secrets → Actions:
   - `OPENAI_API_KEY` = your OpenAI key
   - `RESEND_API_KEY` = your Resend key
3. Update `EMAIL_FROM` in `.github/workflows/daily.yml` with your verified sender.
4. Update `EMAIL_TO` with recipient list.

## Run

- Automatically at 08:30 IST daily.
- Or run manually: Actions tab → "Run workflow".
