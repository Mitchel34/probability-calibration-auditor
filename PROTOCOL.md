# Frozen probability audit protocol

## Public audit interface

`audit(probabilities, outcomes)` accepts built-in lists of equal length 1..10000. Probability exact types int/float exclude bool; values must be finite and within [0,1], checked before conversion to float. Outcomes have exact type int and value 0 or 1. Inputs are not modified. Invalid library inputs raise ValueError("invalid input"). Empty input is invalid. Negative floating zero is accepted.

Return exact keys:
- `schema`: "probability-audit/1"
- `n`: integer input count
- `scores`: exactly `brier, log_loss, gap, ece`, finite floats
- `bins`: four rows, each exactly `lower, upper, upper_inclusive, count, sum_p, sum_y, mean_p, mean_y`

Bounds are floats 0,.25,.5,.75,1, in ascending bin order. Only the last bin has `upper_inclusive=true`. count and sum_y are integers, sum_p a float. Empty bins have zero count/sums and null means. Otherwise means are floating sums divided by count.

## Arithmetic

Use Python binary64 scalar operations in input order; sums start at 0.0 except integer counts/label sums. No intermediate rounding or compensated summation.

For each p,y:
1. Add `(p-y)*(p-y)` to squared-error sum.
2. Compute `c=min(1.0-1e-12,max(1e-12,p))`; add `-(y*log(c)+(1-y)*log(1.0-c))` to log-loss sum, using natural log.
3. Add original p and y to global and assigned bin sums.
4. Bin assignment is 0 if p<.25, else 1 if p<.5, else 2 if p<.75, else 3.

Divide squared-error/loss sums by n. Gap is `abs(sum_p/n-sum_y/n)`. Accumulate ECE in bin order as `(count/n)*abs(sum_p/count-sum_y/count)`, skipping empty bins. Endpoints 0 and 1 remain valid and only log loss clips. Binary64 makes the upper clipping distance slightly different from 1e-12; do not replace it with a symmetric analytical shortcut.

Hand oracles:
| Probabilities | Labels | Brier | Gap | ECE | Log loss |
| --- | --- | --- | --- | --- | --- |
| [0,1] | [0,1] | 0 | 0 | 0 | -log(1-1e-12) |
| [0,1] | [1,0] | 1 | 0 | 1 | -(log(1e-12)+log(1-(1-1e-12)))/2 |
| [.25,.75] | [0,1] | .0625 | 0 | .25 | -log(.75) |
| [.25,.25] | [0,1] | .3125 | .25 | .25 | -(log(.75)+log(.25))/2 |
| [.5,.5] | [0,1] | .25 | 0 | 0 | log(2) |

Hand-oracle comparisons use absolute and relative tolerance 1e-12. Counts, types, key sets, boundaries and repeat equality are exact.

## Bounded JSON CLI

No arguments reads stdin. `--demo` audits demo.json's four static rows; `--help` prints usage. Other argument combinations reject. Module and installed console entry share the same main function.

Input exact keys probabilities/outcomes. Strict UTF-8, no BOM. Maximum 1,048,576 bytes; bounded read requests at most one byte beyond that to detect overflow. A string/escape-aware bracket scan rejects nesting >4 before JSON parsing (root object depth 1). Number token length <=64, duplicate object keys rejected, JSON NaN/Infinity and overflow to infinity rejected. No unknown keys, multiple documents, nested probability elements or coercion of strings/booleans.

Output uses sorted object keys, compact separators, allow_nan=False, shortest full-precision float representation, one trailing LF. Array order fixed. No time or randomness. Invalid input exits 2, empty stdout, stderr `error: invalid input\n`. I/O errors exit 1 with `error: I/O failure\n`; broken pipe exits 1 without a traceback.

## Synthetic workload

For each of two passes, visit seeds [7,23,101] in order. Instantiate random.Random(seed), default integer-seed initialization version 2, for each seed/pass. This uses Python's MT19937 Random.random 53-bit output. For i=0..9 set q=(2*i+1)/20.0. For j=0..19 draw exactly one rng.random(); y=1 iff draw<q. Thus each seed has 200 q-major/repetition-minor rows.

Apply four transforms in order with the exact same outcomes:
- oracle: q
- shrink: 0.5+0.5*(q-0.5)
- expand: min(0.99,max(0.01,0.5+1.5*(q-0.5)))
- reversed: 1.0-q

Call the shared audit implementation per seed/transform. No additional random draws, training, fitting, search, data downloads or replacing observed labels with expectations. Pool first-pass bin counts/sums by ordinary addition of each seed's per-bin values in seed order. The second pass starts fresh PRNG instances and computes all audits again solely for exact equality of data, audit structures and metric dictionaries.

There are 600 unique first-pass outcomes, four methods, 2400 first-pass forecast records, and 4800 total forecast assessments across both passes. Never include repeats in score denominators, seed summaries or pooled statistics.

Exactly 100 metric names and 22 checks are listed in evaluation-contract.json. Names are ordered seed-major, method-major, score-major for 48 seed scores, then method/bin/statistic-major for 48 pooled statistics, then the four accounting values. No packed payloads or extra numeric metrics. Metric/check helpers construct names without generating observations.

## Integrity checks

The 22 checks are:
- exact metric set, all metric values finite excluding Boolean, complete accounting, and full deterministic repeat equality;
- twelve seed/method checks for n=200; four bins; nonnegative integer counts/label sums; labels<=count; total count/labels/probability sum consistency; bin probability sums within count*bin bounds; empty means/sums; finite score bounds and recomputed gap/ECE;
- four method checks for pooled n=600, ordered seed-sum equality, count/label/bin bounds and empty-bin sums;
- paired outcome vectors identical across methods; every forecast matches its fixed transform.

Use abs/rel 1e-12 for sum/formula comparisons and 1e-12 allowance around numerical bounds. Brier/gap/ECE bounds [0,1]; log loss [0,28]. Repeat equality is exact. These are integrity criteria, not empirical winner criteria. Preserve failures and source versions.

## Receipt-only export contract

The exporter imports no core/evaluator. It reads at most 1MiB of strict UTF-8 JSON, with the CLI's number/duplicate/nonfinite rules and max depth 16. Require caller-supplied lowercase 64-hex SHA256 pins for raw receipt, source and runner.

Required exact receipt constants: kind=benchmark-receipt; control_mode=trusted-local-python-operational-v1; outcome=pass; reason=passed; source_sha256/runner_sha256 match pins; process_tree_stopped=true; owned_child_reaped=true; descendants_allowed=false; compute_threads=1; monitor_threads=0; supervisor_threads=1; memory_hard_limit=false; cpu_accounting=at_least_full_reservation_and_observed_usage_no_refund; measured_cpu_is_lower_bound_before_final_receipt_and_db=true. Types are exact, including Boolean/integer distinctions.

cpu_seconds, measured_cpu_before_closeout_seconds, peak_memory_bytes, wall_seconds must be finite nonnegative numbers excluding bool; peak_memory_bytes exact int, charged CPU>=measured. Extra private top-level fields may exist and are discarded.

result exact keys metrics/checks. Metrics exactly the 100 names: seed scores and pooled sum_p exact floats; pooled counts/sum_y and accounting exact ints. Checks exactly 22 entries in manifest order, each exact keys name/passed, each passed Boolean true. Duplicates, reordering and missing/extra entries fail. Accounting exact 600/4/2400/4800. Score bounds as above.

Per method, pooled count in 0..600; integer 0<=sum_y<=count; finite sum_p bounded by bin bounds*count with 1e-12 allowance; zero counts require exactly zero sums. Four counts sum to 600, and all methods share the same pooled total label count. No coercion or replacement.

Public export exact keys schema ("probability-evaluation/1"), metrics, checks, derived, resources. Retain raw metrics and checks unchanged. Do not publish raw receipt extras, paths, IDs or pins.
- derived exact keys seed_summary and pooled_reliability, each object containing exactly the four method names.
- seed_summary[method] contains exactly four scores, each exact object mean/sample_sd finite floats. Mean=sum(values)/3 in seed order; sample_sd=sqrt(sum((x-mean)**2)/2).
- pooled_reliability[method] exact keys n/ece/bins; n=600, bins use the audit schema, means from retained sums only; ECE calculated using count/600 weights.
- resources exact keys charged_cpu_seconds, measured_precloseout_cpu_seconds, peak_memory_bytes, wall_seconds, memory_scope="sum_of_process_high_water_marks", cpu_scope="measured_before_final_closeout; charged_at_least_reservation", memory_hard_limit=false.

Output canonical JSON as above. Markdown follows method, score and bin order and labels summaries/reliability as derived. All 48 scores and 16 pooled rows are shown. Three seed standard deviations are descriptive, not inferential confidence intervals. Pooled ECE need not equal mean seed ECE. Digest/schema verification does not authenticate provenance or prove external operation closeout; verify those separately.

## Reproducibility and resource scope

Pure core.py exposes evaluate() and uses only math/random. A trusted supervisor can validate it and run the full workload in a fresh process. Intended evaluation ceilings: one compute process/thread plus one supervisor, 60 aggregate CPU seconds, 256MiB operational memory and 120 wall seconds. Limits require actual host availability and a qualified runner; they are not hard hostile-code containment claims. Resource reports distinguish measured CPU before final closeout from conservative charged CPU and report conservative summed RSS peaks.

Ordinary checks use smaller independent bounded execution, never evaluate() or the full workload. Tests include clearly invented receipts, not synthetic findings. Clean offline packaging/install verification remains separate and must exercise installed code outside the source directory, validate wheel members/RECORD and source hashes, and use existing tools without network/dependency access.

## Interpretation

Brier/log loss are probability-quality scores rather than calibration-only scores. Mean gap can cancel; ECE changes with bins and finite samples. Positive-class ECE differs from top-label confidence ECE. Paired synthetic data, four fixed transforms and three seeds do not establish real-world calibration, fairness or model superiority. Preserve all measured outcomes without tuning a threshold after observing them.
