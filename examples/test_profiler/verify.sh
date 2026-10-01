#!/usr/bin/env bash
set -euo pipefail

if [[ $(uname -s) != Linux ]]; then
    echo 'verify.sh requires Linux/ELF.' >&2
    exit 1
fi
command -v readelf >/dev/null
build_dir=$(cd "${1:-build}" && pwd)

# 清除影响符号绑定和日志的环境，确保对照结果可重复。
unset LD_PRELOAD LD_LIBRARY_PATH LD_DYNAMIC_WEAK LD_DEBUG LD_AUDIT DEMO_QUIET
scratch_dir=$(mktemp -d)
trap 'rm -rf "$scratch_dir"' EXIT

"$build_dir/app" 3 >"$scratch_dir/baseline.log"
LD_PRELOAD="$build_dir/libprofiler.so" "$build_dir/app" 3 >"$scratch_dir/profiled.log"
DEMO_QUIET=1 LD_PRELOAD="$build_dir/libprofiler.so" \
    "$build_dir/app" 100 >"$scratch_dir/quiet.log"

# 验证调用顺序、业务结果、计数与时间范围；不固定耗时数值。
python3 - "$scratch_dir" <<'PY'
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
baseline = (root / "baseline.log").read_text().splitlines()
profiled = (root / "profiled.log").read_text().splitlines()
quiet = (root / "quiet.log").read_text().splitlines()
original = "[libdemo] original demoAdd(10, 20)"
assert baseline == ["[app] call demoAdd, iterations = 3"] + [original] * 3 + [
    "[app] result = 30, calls = 3, checksum = 90"
], baseline
assert profiled[0] == baseline[0] and profiled[-2] == baseline[-1], profiled
assert len(profiled) == 12, profiled
for i in range(3):
    group = profiled[1 + i * 3:4 + i * 3]
    assert group[:2] == ["[profiler] before demoAdd", original], group
    assert re.fullmatch(r"\[profiler\] after demoAdd, ret = 30, elapsed_ns = \d+", group[2])
assert quiet[:2] == ["[app] call demoAdd, iterations = 100",
                     "[app] result = 30, calls = 100, checksum = 3000"], quiet
assert len(quiet) == 3, quiet
for lines, count in [(profiled, 3), (quiet, 100)]:
    match = re.fullmatch(
        r"\[profiler\] summary: calls=(\d+) total_ns=(\d+) "
        r"avg_ns=([\d.]+) min_ns=(\d+) max_ns=(\d+)", lines[-1])
    assert match, lines[-1]
    calls, total, avg, minimum, maximum = match.groups()
    assert int(calls) == count
    assert int(minimum) * count <= int(total) <= int(maximum) * count
    assert abs(float(avg) - int(total) / count) <= 0.011
print("PASS: call order, return values, quiet mode, counts and timing ranges")
PY

readelf --dyn-syms --wide "$build_dir/libdemo.so" >"$scratch_dir/demo.symbols"
readelf --dyn-syms --wide "$build_dir/libprofiler.so" >"$scratch_dir/profiler.symbols"
python3 - "$scratch_dir" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
def symbol(file, name):
    rows = [line.split() for line in (root / file).read_text().splitlines()]
    matches = [row for row in rows if len(row) == 8 and row[-1] == name]
    assert len(matches) == 1, (file, name, matches)
    return matches[0]

public = symbol("demo.symbols", "demoAdd")
original = symbol("demo.symbols", "pdemoAdd")
wrapper = symbol("profiler.symbols", "demoAdd")
reference = symbol("profiler.symbols", "pdemoAdd")
assert public[3:6] == ["FUNC", "WEAK", "DEFAULT"], public
assert original[3:6] == ["FUNC", "GLOBAL", "DEFAULT"], original
assert public[1] == original[1] and public[6] == original[6] != "UND"
assert wrapper[3:6] == ["FUNC", "GLOBAL", "DEFAULT"] and wrapper[6] != "UND"
assert reference[6] == "UND", reference
print("PASS: weak/global exports, alias address and original reference")
PY

for invalid in 0 -1 abc 3x 1000001 999999999999999999999999; do
    if "$build_dir/app" "$invalid" >"$scratch_dir/invalid.log" 2>&1; then
        echo "Unexpected success for iterations=$invalid" >&2
        exit 1
    else
        status=$?
        [[ $status == 2 ]] || exit 1
    fi
done
if "$build_dir/app" 1 2 >"$scratch_dir/invalid.log" 2>&1; then
    echo 'Unexpected success for extra arguments' >&2
    exit 1
else
    status=$?
    [[ $status == 2 ]] || exit 1
fi
echo 'PASS: invalid arguments'
