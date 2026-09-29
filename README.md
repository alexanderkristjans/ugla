# ics-rewriter

Fetches an .ics calendar every hour, rewrites event titles (and optionally locations/descriptions) using `rules.toml`, and publishes the result on GitHub Pages as a subscribable link.

## Setup (one time)

1. Create a new GitHub repo (e.g. `kalender`) and push these files to `main`.
2. **Settings → Secrets and variables → Actions → New repository secret**
   Name: `ICS_URL`, value: the original calendar link.
3. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. **Actions → Update calendar → Run workflow** to publish the first time.

Your new link is:

```
https://<your-username>.github.io/<repo>/calendar.ics
```

Subscribe to it in Apple/Google Calendar ("Add calendar from URL"). Use `webcal://` instead of `https://` for one-click subscribing on macOS/iOS.

## Changing the rules

Edit `rules.toml` and push — the workflow runs automatically on every change to the rules, and hourly otherwise. Test locally first with:

```
ICS_URL="https://..." python3 rewrite_ics.py
# or on a downloaded file:
python3 rewrite_ics.py --input original.ics --output test.ics
```

## Notes

- The original link is stored as a secret, so it never appears in the repo.
- The published calendar is **public** to anyone who knows the URL. If the contents are private, rename the output to something unguessable (change `calendar.ics` in the workflow to e.g. `k7f2q9x.ics`).
- Google Calendar only refreshes subscribed calendars every 8–24 hours regardless of how often this runs; Apple Calendar lets you pick the interval.
