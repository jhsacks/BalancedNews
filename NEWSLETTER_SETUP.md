# Newsletter setup

The code is complete. The signup list uses Supabase, and email delivery uses Resend. The briefing is generated once and reused for the website and email, so this adds no second AI-generation pass.

## 1. Supabase
Create a Supabase project. Open its SQL editor and run `subscribers.sql` once.

In Streamlit Community Cloud app settings, add these secrets:

```toml
SUPABASE_URL = "your Supabase project URL"
SUPABASE_ANON_KEY = "your Supabase anon key"
```

## 2. Resend
Create a Resend account and verify the domain/address that will send the newsletter.

Add these GitHub Actions repository secrets:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `RESEND_API_KEY`
- `NEWSLETTER_FROM_EMAIL` such as `The Balanced Brief <brief@your-verified-domain.com>`
- `NEWSLETTER_BASE_URL` set to `https://balancednews.streamlit.app/`

Expose those secrets as environment variables in the existing briefing workflow step that runs `python generate_brief.py`:

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
  SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
  RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
  NEWSLETTER_FROM_EMAIL: ${{ secrets.NEWSLETTER_FROM_EMAIL }}
  NEWSLETTER_BASE_URL: ${{ secrets.NEWSLETTER_BASE_URL }}
```

The AM run emails AM and BOTH subscribers. The PM run emails PM and BOTH subscribers. Every email includes the Venmo support link and a personal unsubscribe link.
