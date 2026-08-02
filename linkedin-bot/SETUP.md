# LinkedIn Bot — Setup Guide

This bot posts one AI-generated "swap chart" graphic + caption to your agency's
LinkedIn Company Page automatically, on the schedule you choose. It runs on
GitHub Actions (free tier), same as the Instagram Carousel Bot, but it's a
separate workflow with its own code and its own voice — nothing here touches
the Instagram bot.

Follow these steps in order. Steps 1–4 happen on LinkedIn's site. Steps 5–7
happen on GitHub.

---

## Step 1: Confirm your Company Page exists

1. Go to [linkedin.com/company/setup/new](https://www.linkedin.com/company/setup/new/)
2. If you already have a Company Page for the agency, search for it at the top
   of LinkedIn and open it instead — skip creating a new one.
3. Make sure the page has: a logo, a tagline, and a website URL filled in.
   LinkedIn checks that these are filled in during the API approval step
   below — an empty/unfinished page can get your access request rejected.
4. Note the page's exact name — you'll need it in Step 2.

## Step 2: Create a LinkedIn Developer app

1. Go to [linkedin.com/developers/apps/new](https://www.linkedin.com/developers/apps/new)
2. Fill in:
   - **App name**: something like "R&D Marketing Bot" (avoid using the word
     "LinkedIn" or "In" anywhere in the name — LinkedIn rejects that).
   - **LinkedIn Page**: select the Company Page from Step 1.
   - **App logo**: upload any square logo/image.
3. Check the legal agreement box, click **Create app**.
4. You'll land on your app's dashboard. Click the **Products** tab.

## Step 3: Request Community Management API access

1. On the **Products** tab, find **Community Management API** and click
   **Request access**.
2. LinkedIn will ask you to verify your app against the Company Page — a
   pop-up or banner will prompt "a super admin of this Page must verify
   this app." Since you're the admin, follow that verification prompt (it's
   a one-click confirm on the page's admin settings).
3. Fill out the access request form. It will ask for:
   - A **business email address** (must be a domain email, e.g.
     `ryan@yourdomainhere.ie` — a `@gmail.com` address will fail
     verification. If you don't have one yet, this is worth setting up
     regardless, for outreach credibility).
   - Your organization's legal name, registered address, and website.
   - A short description of your use case — write something like: *"Posting
     original marketing-education content to our own Company Page on a
     schedule, to build audience credibility for our small-business
     marketing agency."*
4. Submit. This is reviewed by LinkedIn — it is **not instant**, but for a
   single self-owned Company Page use case it should clear without needing
   the harder "Standard Tier" screencast review (that tier is only required
   if you're serving other people's LinkedIn accounts, which you're not).
5. Once approved, you'll see **Community Management API — Development Tier**
   listed as an active product on the Products tab. Development Tier is
   enough — you never need Standard Tier for this.

## Step 4: Generate your credentials

You need four values for the bot: **Client ID**, **Client Secret**,
**Refresh Token**, and your **Organization URN**.

1. On your app's **Auth** tab, copy the **Client ID** and **Client Secret** —
   save these somewhere temporary (a notes file), you'll paste them into
   GitHub in Step 7.
2. Still on the **Auth** tab, under **OAuth 2.0 scopes**, confirm
   `w_organization_social` is listed (it's added automatically once
   Community Management API is approved).
3. Use LinkedIn's built-in **Token Generator** tool
   (linked from your app's Auth tab, or directly at
   [linkedin.com/developers/tools/oauth](https://www.linkedin.com/developers/tools/oauth/token-generator)):
   - Select your app.
   - Select the `w_organization_social` scope (and `r_organization_social`
     if offered).
   - Click through the LinkedIn login/consent screen as yourself.
   - The tool will show you an **Access Token** and a **Refresh Token**.
     Copy the **Refresh Token** — that's the one the bot actually needs
     long-term (the access token expires in 60 days; the bot uses the
     refresh token to mint a new access token on every run).
4. Get your **Organization URN**: go to your Company Page admin view, look
   at the URL — it contains a number, e.g.
   `linkedin.com/company/12345678/admin/`. Your URN is
   `urn:li:organization:12345678`.

You now have all four values. Keep them somewhere private — never paste
them into a chat or commit them into the repo itself.

---

## Step 5: Add the bot files to your repo

Go to your existing `Carousel-Bot` repo on GitHub (or wherever your
Instagram bot lives) — the LinkedIn bot can live in the same repo, in its
own folder, so it's all in one place.

1. Click **Add file → Create new file**.
2. In the filename box, type `linkedin-bot/generate_copy.py` (typing the
   `/` creates the folder automatically).
3. Paste in the contents of `generate_copy.py` from the files I've given
   you.
4. Scroll down, click **Commit changes...**, then **Commit changes**.
5. Repeat steps 1–4 for each of these files, adjusting the filename each
   time:
   - `linkedin-bot/generate_image.py`
   - `linkedin-bot/post_linkedin.py`
   - `linkedin-bot/main.py`
   - `linkedin-bot/requirements.txt`
6. For the workflow file, create `.github/workflows/linkedin-bot.yml`
   (this sits alongside your existing Instagram workflow file, not inside
   the `linkedin-bot` folder) and paste in its contents.

## Step 6: Add your secrets

1. In the repo, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret** for each of the following (name on the
   left, exactly as written, value on the right):

   | Secret name | Value |
   |---|---|
   | `LINKEDIN_CLIENT_ID` | from Step 4 |
   | `LINKEDIN_CLIENT_SECRET` | from Step 4 |
   | `LINKEDIN_REFRESH_TOKEN` | from Step 4 |
   | `LINKEDIN_ORG_URN` | from Step 4, e.g. `urn:li:organization:12345678` |

3. `MISTRAL_API_KEY` should already exist as a secret from the Instagram
   bot setup — the LinkedIn bot reuses it, no need to add it again.
4. Optional, for email notifications: if you already have `SMTP_HOST`,
   `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO` set up from the Instagram bot, the
   LinkedIn bot will reuse those too. If not, the bot still works — it just
   skips sending you an email and logs the result in the Actions run
   instead.

## Step 7: Test it

1. Go to the **Actions** tab of your repo.
2. Click **LinkedIn Bot** in the left sidebar.
3. Click **Run workflow → Run workflow** (this triggers it manually,
   without waiting for the schedule).
4. Click into the run to watch the logs. If it fails, the error message in
   the log will say which step broke (usually a wrong secret name or a
   token that wasn't copied correctly) — send me that error and I'll fix
   it.
5. Once a run succeeds, check the Company Page — the post should be live.

The schedule is set to 08:00 UTC daily in the workflow file. Tell me if you
want a different time or fewer days a week, and I'll adjust the `cron`
line.

---

## What each file does

- **`generate_copy.py`** — calls Mistral to write the post: title, subtitle,
  8–10 "what owners say → what actually works" pairs, caption, hashtags.
  Topics rotate across Google Ads / Meta Ads / Email Marketing, framed to
  build credibility with small-business prospects (not generic viral bait).
- **`generate_image.py`** — fetches a free AI illustration (Pollinations.ai,
  no API key needed) and overlays the swap-chart design on top with Pillow,
  matching the format of your best-performing post to date.
- **`post_linkedin.py`** — handles the LinkedIn OAuth token refresh, image
  upload, and post creation.
- **`main.py`** — runs all three in order and emails you the result.
