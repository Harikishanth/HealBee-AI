# Re-push to a new GitHub repo (clean hackathon project)

## 1. Create the new repo on GitHub

1. Go to **https://github.com/new**
2. **Repository name:** e.g. `healbee-hackathon` (or whatever you want)
3. **Private** or **Public** – your choice
4. **Do not** add a README, .gitignore, or license (you already have them)
5. Click **Create repository**

## 2. Point your local repo at the new remote

In your project folder (`HealHub`), run:

```bash
cd c:\HealBee\HealHub

# Replace YOUR_USERNAME and NEW_REPO_NAME with your GitHub username and new repo name
git remote set-url origin https://github.com/YOUR_USERNAME/NEW_REPO_NAME.git

# Verify
git remote -v
```

Example if your username is `Harikishanth` and new repo is `healbee-hackathon`:

```bash
git remote set-url origin https://github.com/Harikishanth/healbee-hackathon.git
```

## 3. Push everything

```bash
git push -u origin main
```

If GitHub asks for auth, use a **Personal Access Token** (Settings → Developer settings → Personal access tokens) as the password, or sign in via browser if prompted.

## 4. Streamlit Cloud

- Go to **share.streamlit.io**
- Either **edit** your existing app and change its source to the new repo (if the UI allows), or
- **New app** → connect GitHub → pick **YOUR_USERNAME/NEW_REPO_NAME**, branch **main**, main file **src/ui.py** (or `main.py` if that’s your entry point)

Done. New repo = your commits only (plus any Cursor commits you make from now on; past “contributors” stay only on the old repo).
