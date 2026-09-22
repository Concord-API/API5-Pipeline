#!/usr/bin/env bash

BOARD_OWNER="Concord-API"
BOARD_REPO="Concord-API/API-5"
BOARD_NUMBER=5

task_id() {
  if [[ "$1" =~ ^([0-9]+\.[0-9]+)- ]]; then
    echo "${BASH_REMATCH[1]}"
  else
    return 1
  fi
}

target_status() {
  case "$1" in
    branch) echo "In Progress" ;;
    opened) echo "Review" ;;
    closed)
      if [[ "$2" == "true" ]]; then
        echo "Done"
      else
        echo "In Progress"
      fi
      ;;
    *) return 1 ;;
  esac
}

other_pull_request_open() {
  local issue="$1" current="$2" url
  while read -r url || [[ -n "$url" ]]; do
    if [[ -n "$url" && "$url" != "$current" ]] && [[ "$(gh pr view "$url" --json state --jq .state)" == "OPEN" ]]; then
      return 0
    fi
  done < <(gh issue view "$issue" -R "$BOARD_REPO" --json comments --jq '.comments[].body' | sed -n 's/^Pull request: //p')
  return 1
}

main() {
  set -euo pipefail

  local id
  if ! id="$(task_id "$BRANCH")"; then
    echo "Branch $BRANCH does not follow the task pattern"
    return 0
  fi

  local issue
  issue="$(gh issue list -R "$BOARD_REPO" --state all --search "\"$id\" in:title" --json number,title \
    --jq "[.[] | select(.title | startswith(\"$id \"))][0].number // empty")"
  if [[ -z "$issue" ]]; then
    echo "::warning::No issue titled '$id ...' in $BOARD_REPO"
    return 0
  fi

  local status project field option item
  status="$(target_status "$EVENT" "$MERGED")"
  if [[ "$EVENT" == "closed" ]] && other_pull_request_open "$issue" "${PR_URL-}"; then
    status="Review"
  fi
  project="$(gh project view "$BOARD_NUMBER" --owner "$BOARD_OWNER" --format json --jq .id)"
  read -r field option < <(gh project field-list "$BOARD_NUMBER" --owner "$BOARD_OWNER" --format json \
    --jq ".fields[] | select(.name == \"Status\") | .id + \" \" + (.options[] | select(.name == \"$status\") | .id)")
  item="$(gh project item-add "$BOARD_NUMBER" --owner "$BOARD_OWNER" --url "https://github.com/$BOARD_REPO/issues/$issue" --format json --jq .id)"
  gh project item-edit --id "$item" --project-id "$project" --field-id "$field" --single-select-option-id "$option" >/dev/null
  echo "Issue #$issue moved to $status"

  if [[ "$EVENT" == "opened" && -n "${PR_URL-}" ]]; then
    local comment="Pull request: $PR_URL"
    if ! gh issue view "$issue" -R "$BOARD_REPO" --json comments --jq '.comments[].body' | grep -qxF -- "$comment"; then
      gh issue comment "$issue" -R "$BOARD_REPO" --body "$comment" >/dev/null
    fi
  fi

  if [[ "$status" == "Done" ]]; then
    gh issue close "$issue" -R "$BOARD_REPO" --reason completed >/dev/null
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
