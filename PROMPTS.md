# Prompt log

Every prompt I sent to an AI assistant while building this project, in order. Tool, prompt, and
what I did with the result.

Add a new row for every further prompt (fixes after review, deployment help, and so on) before
submitting.

| # | Date (IST) | Tool | Prompt | What I did with the answer |
|---|---|---|---|---|
| 1 | 2026-10-17 | Claude Code (Claude Opus 5.5), desktop app | Pasted the assignment email, attached `KJBN_Internship_Problem_3.pdf` and `KJBN_Internship_Common_Instructions_and_Evaluation.pdf`, and wrote: *"build the whole project fully, "C:\Users\Janani\OneDrive\Desktop\kjpn" this is the folder … then think carefully and build dont use your cached memory think and do uniquely"* | The assistant produced the full repository in milestone commits M0–M6: schema and migration, pure domain rules, services with locking, API, tests, React UI, Docker/Render/Vercel/CI files, README and SUBMISSION drafts. **Used.** *(Before submitting, update this note with what you reviewed, changed or rejected.)* |
| 2 | 2026-10-17 | Claude Code (Claude Opus 5.5), desktop app | *"Deploy using README section 5a: create a Neon database, then a Render Blueprint for the API, then a Vercel project with root directory frontend. Then fill in the live links in README section 2. how to do this?"* | Got step-by-step instructions for GitHub push, Neon, Render, Vercel and CORS setup. **Used** as my deployment checklist. |
| 3 | 2026-10-17 | Claude Code (Claude Opus 5.5), desktop app | Gave my name, email and the GitHub repo URL (`https://github.com/DurgaNandhini26/warehouse-stock-ledger.git`). | The assistant set the repo's git identity, corrected the author name on the not-yet-pushed commits (dates unchanged), updated the commit hashes in SUBMISSION.md, and pushed to GitHub. **Used.** |
| 4 | 2026-10-18 | Claude Code (Claude Opus 5.5), desktop app | *(Neon connection string pasted, with the text "this is")* | The assistant used it to migrate and seed Neon and verify it read-only. I learned the password is a secret and should be reset. **Used.** |
| 5 | 2026-10-18 | Claude Code (Claude Opus 5.5), desktop app | *(Screenshot: Render "Failed deploy")* | Got a `render.yaml` fix (explicit Docker paths from the repo root), which was pushed. **Used.** |
| 6 | 2026-10-18 | Claude Code (Claude Opus 5.5), desktop app | *(Pasted Render log: `invalid channel_binding value: "require this is"`)* | Learned I had pasted extra words into `DATABASE_URL`; fixed the value in Render. **Used.** |
| 7 | 2026-10-18 | Claude Code (Claude Opus 5.5), desktop app | *(Screenshot: Render deploy succeeded)* | The assistant tried the default URL, which didn't exist, and asked me for the real one. **Used.** |
| 8 | 2026-10-18 | Claude Code (Claude Opus 5.5), desktop app | *"i cant find api url"* | Got directions to the URL on the Render service page. **Used.** |
| 9 | 2026-10-18 | Claude Code (Claude Opus 5.5), desktop app | `https://stock-ledger-api-ec7c.onrender.com` | The assistant checked the live API, found broken JSON was reported against field "12", fixed it with a test, and pushed. **Used.** |
| 10 | 2026-10-20 | Claude Code (Claude Opus 5.5), desktop app | *(Screenshot: Vercel project showing 404, source "Vercel Drop")* | Learned Vercel Drop uploads unbuilt files; got steps to connect the Git repo with root `frontend`. **Used.** |
| 11 | 2026-10-20 | Claude Code (Claude Opus 5.5), desktop app | *(Screenshot: Vercel Root Directory = frontend)* "next?" | Got the next steps (framework, env var, deploy). **Used.** |
| 12 | 2026-10-20 | Claude Code (Claude Opus 5.5), desktop app | *(Screenshot: env var key with red border)* | Got likely causes for the validation error. **Did not solve it.** |
| 13 | 2026-10-20 | Claude Code (Claude Opus 5.5), desktop app | *"what is next this above is not working i will finsij rest of it and come"* | The assistant committed `frontend/.env.production` so the build no longer needs the dashboard variable, and pushed. **Used.** |
| 14 | 2026-10-20 | Claude Code (Claude Opus 5.5), desktop app | *(Screenshot: env var form with warning, type Secret)* "what to do?" | Learned `VITE_` vars must be type Config, or can be skipped. **Used.** |
| 15 | 2026-10-20 | Claude Code (Claude Opus 5.5), desktop app | *(Screenshot: Vercel deploy dialog, commit a9f3cd4 already production)* | The assistant verified the UI loads and found the CORS preflight still failing; I updated `CORS_ORIGINS` in Render. **Used.** |
| 16 | 2026-10-21 | Claude Code (Claude Opus 5.5), desktop app | *"i have done it in render"* | The assistant verified CORS for every UI call, filled the README/SUBMISSION live links, logged these prompts and tagged `v1.0`. **Used.** |
| 17 | 2026-10-21 | Claude Code (Claude Opus 5.5), desktop app | *"ok email give me"* | Got a draft reply email with my details and all links. **Used**, with my phone number added. |
| 18 | 2026-10-21 | Claude Code (Claude Opus 5.5), desktop app | *"how to open ui and do what?"* | Got a 10-step manual test plan for the live site, with expected results. **Used** as a checklist. |
| 19 | 2026-10-21 | Claude Code (Claude Opus 5.5), desktop app | *"u itself"* | The assistant ran that plan on the live site: over-dispatch, zero cost, same-bin transfer, 'other' without a note, reversal, ledger maths, CSV, reports and reconcile. Via the API it checked double reversal, reversing a reversal, two racing OUTs (one 201, one 409; the winner was reversed afterwards) and 18 malformed requests (no 5xx). All passed; test movements #30–#36 are marked 'QA check'. **Used.** |
