# Deployment - GitHub and Streamlit Community Cloud

This guide applies to the repository root, which contains `app.py`, `requirements.txt`, `docuguard/`, `tests/`, and `sample-data/`.

## 1. Verify your local build

From a terminal in the project directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m docuguard.evaluate_samples
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On Windows the environment can be activated with `.\.venv\Scripts\Activate.ps1`, but activation is optional when calling `.\.venv\Scripts\python.exe` directly. The expected baseline counts are **2 Approve / 5 Reject / 3 Needs a person to check**. Test both CSV exports and the **Document evidence** tab before publishing.

## 2. Publish the repository

Create a **public** empty GitHub repository (for example `docuguard-ai`), without auto-generating another README or `.gitignore`.

```powershell
git init -b main
git add .
git status --short
git diff --cached --name-only
```

**Review staged files before the commit.** Do not commit `.venv`, `.env`, generated CSVs, backup ZIPs, personal documents, model weights, or the internal assessment brief. If that brief is already tracked, remove it from the index with `git rm --cached ORIGINAL_TASK_BRIEF.md` (do not remove the original source files from the assessment sample directory).

```powershell
git commit -m "Release DocuGuard evidence-grounded compliance checker"
git remote add origin https://github.com/YOUR-USERNAME/docuguard-ai.git
git push -u origin main
```

Replace the example remote URL with the one GitHub supplies. If Git is already initialized or a remote exists, inspect `git status` and `git remote -v` first rather than reinitializing or adding duplicates. Verify the public repository in an incognito browser.

## 3. Deploy the deterministic demonstration

1. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub.
2. Create an app using the repository's `main` branch, file **`app.py`**.
3. In Advanced settings select **Python 3.12**.
4. No secrets, external AI credentials or GPU are required for the baseline demo.
5. Deploy and test all ten results, document evidence and both CSV exports.
6. In **Local AI review**, an unavailable Ollama notice is expected. That model is **not hosted**. Demonstrate it locally in the Loom recording.
7. Add the **real, verified** live app URL to your GitHub README and submission email.

If hosted deployment fails, include the public GitHub link and record a working local app. The assignment describes a working demo link as optional *if available*; it still requires the code/README, one-page note and a Loom recording no longer than five minutes.

## 4. Final submission checklist

- [ ] GitHub repository opens in a private/incognito browser.
- [ ] `git status` has no private, environment, or backup files staged.
- [ ] Local automated tests and ten-case evaluation pass after the final patch.
- [ ] Hosted app works (or clearly disclose that a hosted demo is unavailable).
- [ ] One-page note includes build, tests, results, limitations and next steps.
- [ ] Five-minute Loom demo shows a rejection, a human-review case, source evidence, and optional local model behavior.
- [ ] Every submitted link opens and has appropriate viewing permissions.
