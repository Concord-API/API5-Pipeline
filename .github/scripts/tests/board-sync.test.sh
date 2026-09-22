#!/usr/bin/env bash
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/../board-sync.sh"
failures=0

fail() {
  echo "FAIL: $1"
  failures=$((failures + 1))
}

assert_eq() {
  if [[ "$2" != "$3" ]]; then
    fail "$1 (expected '$2', got '$3')"
  fi
}

assert_contains() {
  if ! grep -qF -- "$2" <<<"$3"; then
    fail "$1 (missing '$2')"
  fi
}

assert_not_contains() {
  if grep -qF -- "$2" <<<"$3"; then
    fail "$1 (unexpected '$2')"
  fi
}

sandbox="$(mktemp -d)"
trap 'rm -rf "$sandbox"' EXIT
mkdir -p "$sandbox/bin"
cat >"$sandbox/bin/gh" <<'EOF'
#!/usr/bin/env bash
echo "gh $*" >>"$GH_LOG"
case "$1 $2" in
  "issue list") printf '%s' "${FAKE_ISSUE-}" ;;
  "issue view") printf '%s' "${FAKE_COMMENTS-}" ;;
  "project view") echo "PVT_1" ;;
  "project field-list") echo "FIELD_1 OPTION_1" ;;
  "project item-add") echo "ITEM_1" ;;
  "pr view") echo "${FAKE_PR_STATE-MERGED}" ;;
esac
EOF
chmod +x "$sandbox/bin/gh"

run() {
  export GH_LOG="$sandbox/gh.log"
  : >"$GH_LOG"
  output="$(PATH="$sandbox/bin:$PATH" env "$@" bash "$script" 2>&1)"
  status=$?
  calls="$(cat "$GH_LOG")"
}

source "$script"

assert_eq "task id from a foundation branch" "0.12" "$(task_id 0.12-Create-the-dw-schema-migration)"
assert_eq "task id from a story branch" "21.3" "$(task_id 21.3-Show-the-related-doctrine)"
for branch in us1 us0 main RATIO-DOCS-Contribution-Standards 0.12 release-workflow; do
  if task_id "$branch" >/dev/null; then
    fail "no task id for $branch"
  fi
done

assert_eq "branch push" "In Progress" "$(target_status branch false)"
assert_eq "pull request opened" "Review" "$(target_status opened false)"
assert_eq "pull request merged" "Done" "$(target_status closed true)"
assert_eq "pull request closed without merge" "In Progress" "$(target_status closed false)"

run EVENT=branch BRANCH=us1 MERGED=false PR_URL= FAKE_ISSUE=102
assert_eq "branch outside the pattern exits cleanly" "0" "$status"
assert_eq "branch outside the pattern leaves the board alone" "" "$calls"

run EVENT=branch BRANCH=9.9-Missing MERGED=false PR_URL= FAKE_ISSUE=
assert_eq "missing issue exits cleanly" "0" "$status"
assert_contains "missing issue warns" "::warning::" "$output"
assert_not_contains "missing issue leaves the board alone" "project item-edit" "$calls"

run EVENT=branch BRANCH=0.12-Create-the-dw-schema MERGED=false PR_URL= FAKE_ISSUE=102
assert_eq "branch push succeeds" "0" "$status"
assert_contains "branch push adds the issue to the board" "project item-add 5 --owner Concord-API --url https://github.com/Concord-API/API-5/issues/102" "$calls"
assert_contains "branch push moves the card" "project item-edit --id ITEM_1 --project-id PVT_1 --field-id FIELD_1 --single-select-option-id OPTION_1" "$calls"
assert_contains "branch push looks up In Progress" '"In Progress"' "$calls"
assert_not_contains "branch push does not comment" "issue comment" "$calls"

pr="https://github.com/Concord-API/API5-Backend/pull/7"
run EVENT=opened BRANCH=0.12-Create-the-dw-schema MERGED=false PR_URL="$pr" FAKE_ISSUE=102 FAKE_COMMENTS=
assert_contains "opened looks up Review" '"Review"' "$calls"
assert_contains "opened comments the pull request" "issue comment 102 -R Concord-API/API-5 --body Pull request: $pr" "$calls"

run EVENT=opened BRANCH=0.12-Create-the-dw-schema MERGED=false PR_URL="$pr" FAKE_ISSUE=102 FAKE_COMMENTS="Pull request: $pr"
assert_not_contains "reopened does not repeat the comment" "issue comment" "$calls"

run EVENT=closed BRANCH=0.12-Create-the-dw-schema MERGED=true PR_URL="$pr" FAKE_ISSUE=102
assert_contains "merged looks up Done" '"Done"' "$calls"
assert_contains "merged closes the issue" "issue close 102 -R Concord-API/API-5 --reason completed" "$calls"

run EVENT=closed BRANCH=0.12-Create-the-dw-schema MERGED=false PR_URL="$pr" FAKE_ISSUE=102
assert_contains "closed without merge looks up In Progress" '"In Progress"' "$calls"
assert_not_contains "closed without merge keeps the issue open" "issue close" "$calls"

other="https://github.com/Concord-API/API5-Frontend/pull/3"
linked="$(printf 'Pull request: %s\nPull request: %s' "$pr" "$other")"

run EVENT=closed BRANCH=0.12-Create-the-dw-schema MERGED=true PR_URL="$pr" FAKE_ISSUE=102 FAKE_COMMENTS="$linked" FAKE_PR_STATE=OPEN
assert_contains "merged with another open pull request checks it" "pr view $other" "$calls"
assert_not_contains "merged does not check its own pull request" "pr view $pr" "$calls"
assert_contains "merged with another open pull request stays in Review" '"Review"' "$calls"
assert_not_contains "merged with another open pull request keeps the issue open" "issue close" "$calls"

run EVENT=closed BRANCH=0.12-Create-the-dw-schema MERGED=true PR_URL="$pr" FAKE_ISSUE=102 FAKE_COMMENTS="$linked" FAKE_PR_STATE=MERGED
assert_contains "merged after every pull request looks up Done" '"Done"' "$calls"
assert_contains "merged after every pull request closes the issue" "issue close 102" "$calls"

run EVENT=closed BRANCH=0.12-Create-the-dw-schema MERGED=true PR_URL="$pr" FAKE_ISSUE=102 FAKE_COMMENTS="$linked" FAKE_PR_STATE=CLOSED
assert_contains "abandoned pull requests do not block Done" '"Done"' "$calls"

run EVENT=closed BRANCH=0.12-Create-the-dw-schema MERGED=false PR_URL="$pr" FAKE_ISSUE=102 FAKE_COMMENTS="$linked" FAKE_PR_STATE=OPEN
assert_contains "closed without merge with another open pull request stays in Review" '"Review"' "$calls"

if ((failures > 0)); then
  echo "$failures failure(s)"
  exit 1
fi
echo "all board sync tests passed"
