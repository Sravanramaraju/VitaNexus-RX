# VitaNexus-RX project workflow

## Git delivery requirement

- Treat local implementation and GitHub delivery as one workflow for every completed project change.
- After a change is verified, split the work into multiple coherent commits when the work contains independently meaningful concerns (for example: model/API contract, clinical safety logic, UI, tests, and documentation).
- Use descriptive conventional-style commit subjects and commit bodies that explain the behavior, safety implications, and verification performed.
- Push completed commits to the configured `origin` remote on the current task branch before reporting completion.
- Do not create artificial one-line commits merely to increase the commit count; each commit must build and represent a reviewable unit.
- Never commit `.env` files, credentials, access tokens, local caches, rendered QA scratch directories, dependency folders, or generated build output.
- If authentication, branch protection, merge conflicts, failing verification, or an unavailable remote prevents a push, report that explicitly instead of claiming GitHub delivery succeeded.
