#!/usr/bin/env bash
#
# merge_our_prs.sh
# Merge our upstream PRs into main_plus_our_prs, resolving/reporting conflicts,
# then verify containment. Does NOT push (prints the push command at the end).
#
# Usage:
#   ./merge_our_prs.sh          # run the full flow
#   ./merge_our_prs.sh verify   # only re-run the containment check
#
set -uo pipefail

REPO="/Users/benjaminbrumbaugh/Documents/Hermes-Agent"
BRANCH="main_plus_our_prs"
PRS=(88672 89432 91872 98792 99797 100665 102037 103154 106169 106457 106838 106839 107182)

cd "$REPO" || { echo "!! cannot cd to $REPO"; exit 1; }

# --- helpers ---------------------------------------------------------------
pr_ref() { echo "refs/remotes/upstream/pr/$1"; }

# Is PR $1 already contained in ref $2 (as a merge OR via squashed/cherry-picked patches)?
contained_in() {
  local tip ref="$2"
  tip=$(git rev-parse -q --verify "$(pr_ref "$1")" 2>/dev/null) || return 2  # 2 = no local ref
  if git merge-base --is-ancestor "$tip" "$ref" 2>/dev/null; then return 0; fi
  [ -z "$(git cherry "$ref" "$tip" 2>/dev/null | grep '^+')" ] && return 0
  return 1
}

verify() {
  echo "==================== containment report ===================="
  local missing=0
  for pr in "${PRS[@]}"; do
    if contained_in "$pr" "$BRANCH"; then
      echo "PR $pr: OK (in $BRANCH)"
    elif [ $? -eq 2 ]; then
      echo "PR $pr: ?? no local ref refs/remotes/upstream/pr/$pr (fetch it)"
      missing=$((missing+1))
    elif contained_in "$pr" upstream/main; then
      echo "PR $pr: OK (already in upstream/main)"
    else
      echo "PR $pr: >>> MISSING <<<"
      missing=$((missing+1))
    fi
  done
  echo "============================================================"
  return $missing
}

# --- verify-only mode ------------------------------------------------------
if [ "${1:-}" = "verify" ]; then
  git fetch origin "$BRANCH" >/dev/null 2>&1
  git fetch upstream       >/dev/null 2>&1
  verify
  exit $?
fi

# --- 1. sync branch --------------------------------------------------------
echo ">>> checking out $BRANCH and syncing"
git checkout "$BRANCH"            || { echo "!! checkout failed"; exit 1; }
git fetch origin                  || { echo "!! fetch origin failed"; exit 1; }
git fetch upstream                || { echo "!! fetch upstream failed"; exit 1; }

# --- 2. safety checks ------------------------------------------------------
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "!! working tree has tracked changes. Commit/stash first, then re-run."
  git status --short --untracked-files=no
  exit 1
fi

if ! git pull --ff-only; then
  echo "!! branch could not fast-forward — origin/$BRANCH has diverged."
  echo "   Reconcile manually before merging so we don't clobber remote work."
  git rev-list --left-right --count "$BRANCH...origin/$BRANCH"
  exit 1
fi

read -r LOCAL_AHEAD REMOTE_AHEAD < <(git rev-list --left-right --count "$BRANCH...origin/$BRANCH")
echo ">>> divergence local/remote: $LOCAL_AHEAD / $REMOTE_AHEAD"
if [ "${REMOTE_AHEAD:-0}" != "0" ]; then
  echo "!! origin/$BRANCH is ahead by $REMOTE_AHEAD commit(s). Reconcile first."
  exit 1
fi

# --- 3. merge each PR ------------------------------------------------------
for pr in "${PRS[@]}"; do
  if contained_in "$pr" "$BRANCH"; then
    echo ">>> PR $pr already present — skipping"
    continue
  fi
  ref="$(pr_ref "$pr")"
  if ! git rev-parse -q --verify "$ref" >/dev/null; then
    echo "!! PR $pr: no local ref $ref."
    echo "   Fetch it, e.g.: git fetch upstream pull/$pr/head:$ref"
    echo "   Then re-run this script (it resumes and skips what's done)."
    exit 1
  fi
  echo ">>> merging PR $pr"
  if ! git merge --no-edit -m "Merge upstream/pr/$pr into $BRANCH" "$ref"; then
    echo ""
    echo "!! CONFLICT merging PR $pr. Conflicted files:"
    git diff --name-only --diff-filter=U
    echo ""
    echo "   Resolve them, then:"
    echo "     git add -A && git commit --no-edit"
    echo "   To abort just this merge:"
    echo "     git merge --abort"
    echo "   Then re-run ./merge_our_prs.sh (it resumes and skips completed PRs)."
    exit 2
  fi
done

# --- 4. verify -------------------------------------------------------------
echo ""
verify
rc=$?

# --- 5. next step (no auto-push) ------------------------------------------
echo ""
if [ "$rc" -eq 0 ]; then
  echo ">>> All PRs contained. Review the log, then push when ready:"
  echo "      git log --oneline --graph -20"
  echo "      git push origin $BRANCH"
else
  echo ">>> $rc PR(s) still not contained — see report above."
fi
exit $rc
