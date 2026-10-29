#!/usr/bin/env bash
# Regression cases for skills/manager/scripts/dag.py: one case per fix (tier default, invalid
# tier message, all error classes, unknown-id messages, stray top-level key, path#symbol scopes,
# plan, add). Every case must FAIL on the dag.py of commit 1dbc833 and PASS on the current one.
# Usage: test/test-dag.sh ; DAG=path/to/dag.py test/test-dag.sh to run against another copy.
set -u
DAG=${DAG:-$(cd "$(dirname "$0")/.." && pwd)/skills/manager/scripts/dag.py}
PY=${PYTHON:-python3}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
g="$tmp/g.json"
case_pass=0
case_bad=0
assert_pass=0
assert_bad=0

run() { # run dag.py with the test graph as GRAPH
  out=$("$PY" "$DAG" "$1" "$g" "${@:2}" 2>"$tmp/err")
  code=$?
  err=$(cat "$tmp/err")
}
begin() { echo "== case $1: $2"; cur=$1; cur_bad=0; }
end() {
  if [ "$cur_bad" -eq 0 ]; then case_pass=$((case_pass+1)); echo "case $cur PASS"
  else case_bad=$((case_bad+1)); echo "case $cur FAIL"; fi
}
is() { # want got desc
  if [ "$1" = "$2" ]; then assert_pass=$((assert_pass+1)); echo "  PASS $3"
  else assert_bad=$((assert_bad+1)); cur_bad=1; echo "  FAIL $3: want <$1> got <$2>"; fi
}
has() { # haystack needle desc
  case $1 in
    *"$2"*) assert_pass=$((assert_pass+1)); echo "  PASS $3";;
    *) assert_bad=$((assert_bad+1)); cur_bad=1; echo "  FAIL $3: <$2> missing from <$1>";;
  esac
}

begin 1 "a missing tier is senior (S26)"
echo '{"nodes": {"a": {}}}' > "$g"
run check
is 0 "$code" "check exits 0"
echo '{"nodes": {"a": {"state": "failed"}}}' > "$g"
run escalate a
is "a: senior -> principal" "$out" "escalate starts at senior"
end

begin 2 "an invalid tier reports the value (S26)"
echo '{"nodes": {"a": {"tier": "chief"}}}' > "$g"
run check
is 1 "$code" "check exits 1"
has "$err" "node a: invalid tier chief" "message names the bad value"
end

begin 3 "check reports every error class (S27)"
echo '{"nodes": {"nt": {"tier": "chief"}, "x": {"files": ["f"]}, "y": {"files": ["f"]}, "c": {"deps": ["d"]}, "d": {"deps": ["c"]}}}' > "$g"
run check
is 1 "$code" "check exits 1"
has "$err" "invalid tier" "tier class reported"
has "$err" "file overlap" "overlap class reported"
has "$err" "cycle" "cycle class reported"
end

begin 4 "an unknown id reports unknown node (S28)"
echo '{"nodes": {"a": {"tier": "junior"}}}' > "$g"
before=$(cat "$g")
run done zzz
is 1 "$code" "done exits 1"
is "unknown node zzz" "$err" "done names unknown node"
is "$before" "$(cat "$g")" "graph unchanged"
echo '{"nodes": {"a": {"tier": "junior"}}, "b": {"tier": "junior"}}' > "$g"
run start b
has "$err" "unknown node b" "start of a stray key names unknown node"
end

begin 5 "check warns on a stray top-level key (S29)"
echo '{"nodes": {"a": {"tier": "junior"}}, "b": {"tier": "junior"}}' > "$g"
run check
is 0 "$code" "check still exits 0"
has "$err" "stray top-level key b" "warning names the key"
end

begin 6 "path#symbol scopes decide overlap (port from manager-1.5.0)"
echo '{"nodes": {"x": {"files": ["a.py"], "tier": "junior"}, "y": {"files": ["a.py#f"], "tier": "junior"}}}' > "$g"
run check
is 1 "$code" "bare path overlaps its symbols: check exits 1"
has "$err" "file overlap: a.py written by x (a.py) and y (a.py#f)" "overlap names both entries"
echo '{"nodes": {"x": {"files": ["a.py#"], "tier": "junior"}}}' > "$g"
run check
is 1 "$code" "empty symbol: check exits 1"
has "$err" "empty symbol in files entry: x a.py#" "empty symbol rejected"
echo '{"nodes": {"x": {"files": ["a.py#f"], "tier": "junior"}, "y": {"files": ["a.py#g"], "tier": "junior"}}}' > "$g"
run check
is 0 "$code" "different symbols of one file coexist"
end

begin 7 "plan reports levels and width (port from manager-1.5.0)"
echo '{"nodes": {"a": {}, "b": {"deps": ["a"]}, "c": {"deps": ["a"]}, "d": {"deps": ["b", "c"]}}}' > "$g"
before=$(cat "$g")
run plan
is 0 "$code" "plan exits 0"
is "L0: a
L1: b c
L2: d
width=2 critical_path=3" "$out" "levels, width, critical path"
is "$before" "$(cat "$g")" "plan is read-only"
end

begin 8 "add appends a todo node and runs check (S30)"
echo '{"nodes": {"a": {"tier": "junior"}}}' > "$g"
run add c --deps a --files x,y --resources r --tier junior
is 0 "$code" "add exits 0"
run check
is 0 "$code" "the result passes check"
is True "$("$PY" -c 'import json,sys; n=json.load(open(sys.argv[1]))["nodes"]["c"]; print(n == {"deps": ["a"], "files": ["x","y"], "resources": ["r"], "state": "todo", "tier": "junior"})' "$g")" "node fields as passed"
before=$(cat "$g")
run add c
is 1 "$code" "a duplicate id is refused"
run add d --tier chief
is 1 "$code" "a bad tier is refused"
has "$err" "node d: invalid tier chief" "the check message names the node"
is False "$("$PY" -c 'import json,sys; print("d" in json.load(open(sys.argv[1]))["nodes"])' "$g")" "a refused add writes nothing"
is "$before" "$(cat "$g")" "graph unchanged by the refusals"
end

echo "== $case_pass cases passed, $case_bad failed; $assert_pass assertions passed, $assert_bad failed"
[ "$case_bad" -eq 0 ]
