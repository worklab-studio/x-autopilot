# Private GitHub Release Guide

This project is set up for paid/private distribution (for example Gumroad + private GitHub access).

## 1. Initialize git locally

```bash
git init
git add .
git commit -m "Initial private release"
```

## 2. Create private GitHub repository

Using GitHub CLI:

```bash
gh repo create twitter-agent --private --source . --remote origin --push
```

Or manually in GitHub UI:
1. Create a new repository (Private).
2. Do not initialize with README.
3. Connect and push:

```bash
git remote add origin git@github.com:<your-username>/twitter-agent.git
git branch -M main
git push -u origin main
```

## 3. Gumroad delivery model

Recommended flow:
1. Sell product on Gumroad.
2. Ask buyer for GitHub username in purchase form.
3. Add buyer as collaborator to private repo.
4. Remove access on refund/cancel.

Important:
- Once someone can clone the repo, code can be copied.
- Use legal terms in `LICENSE` and product description to define usage rights.

## 4. Optional automation

Automate access with:
- Gumroad webhook
- Small backend script that calls GitHub API to add/remove collaborators

## 5. Pre-publish safety checklist

- `.env` is not committed.
- `data/` is ignored except `data/.gitkeep`.
- `venv/` and `dashboard/node_modules/` are ignored.
- `.env.example` has placeholders only (no real keys).
- Repo visibility is set to private.

