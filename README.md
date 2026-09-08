# The Balanced Brief

A ready-to-deploy Streamlit news site. The newest edition is the main view. Every dated AM/PM edition remains selectable in the sidebar.

## Upload and deploy
1. Create a new GitHub repository.
2. Upload all files and folders in this package, including `.github` and `.streamlit`, to the `main` branch.
3. In GitHub, open **Actions**, enable workflows if prompted, select **Generate dated news brief**, then **Run workflow**.
4. Sign in to Streamlit Community Cloud with GitHub, select **Create app**, choose the repository and `app.py`, then deploy.

## Optional AI editing
The site works without an API key by using publisher headlines and summaries. For calm rewrites and balanced context, add a GitHub Actions repository secret named `OPENAI_API_KEY`, then run the workflow again. Never place the key in code.

## Archive
Each run creates `data/briefings/YYYY-MM-DD_AM.json` or `YYYY-MM-DD_PM.json`. This gives the sidebar Monday AM, Monday PM, Tuesday AM, Tuesday PM, and so on. Files remain until you delete them.

## Notes
The workflow checks at 6 AM and 4 PM America/New_York, accounting for daylight saving time. GitHub scheduled jobs may run a little after the target time. Review each publisher's RSS and image reuse terms before broad public distribution.
