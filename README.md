# Probability Calibration Auditor

A dependency-free Python library and strict JSON CLI for paired binary probabilities and outcomes. It reports Brier score, clipped natural-log loss, absolute mean calibration gap, positive-class expected calibration error (ECE), and four reliability bins.

Requires Python 3.11 or newer. No training, calibration fitting, downloaded data, model service, or external dependencies.

## Try the four-row demo

From a source checkout:

```sh
PYTHONPATH=src python3 -m probability_calibration_auditor --demo
PYTHONPATH=src python3 -m probability_calibration_auditor < demo.json
```

Both commands audit the same four fixed rows. Expected Brier score is 0.28125, mean gap is zero, and ECE is 0.375. This is a hand-calculated example, not an evaluation result.

Library usage:

```python
from probability_calibration_auditor import audit

report = audit([0.25, 0.75], [0, 1])
assert report["scores"]["brier"] == 0.0625
```

Default CLI input is one UTF-8 JSON object:

```json
{"probabilities":[0.25,0.75],"outcomes":[0,1]}
```

There must be 1–10,000 paired rows. Probabilities are finite numbers in [0,1]; outcomes are integer 0 or 1. Booleans, floating-point labels, duplicate keys, unknown fields, nonfinite values, oversized input and excessive nesting are rejected. Invalid input returns exit 2, empty stdout, and a generic error on stderr. See [PROTOCOL.md](PROTOCOL.md) for exact limits and schema.

## What the scores mean

| Diagnostic | Definition | Important limitation |
| --- | --- | --- |
| Brier | Mean squared probability error | Measures overall probability quality, not calibration alone |
| Log loss | Mean negative natural log probability of the observed label | Clips only for this score; endpoint mistakes remain very costly |
| Gap | Absolute difference between mean probability and positive-label frequency | Opposite errors can cancel |
| ECE | Count-weighted absolute bin mean probability–frequency difference | Depends on bins and finite sample; this is positive-class ECE |

Bins are [0,.25), [.25,.5), [.5,.75), [.75,1]. The report includes count, probability sum, label sum, and means for each bin; empty-bin means are null. All metrics except log loss use original, unclipped probabilities.

## Tests and evaluation are separate

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

Tests use hand oracles, input rejection cases, and explicitly invented receipt fixtures. They never call the full evaluator. Fixture output is not evidence of scientific performance.

The reproducible synthetic protocol uses seeds 7, 23, 101; 200 Bernoulli outcomes per seed; four fixed probability transforms; and one complete deterministic repeat. The evaluator is `core.evaluate()`. It returns exactly 100 numeric measurements and 22 named integrity checks. It shares the actual library scoring code. Use a separate, bounded trusted execution supervisor for this workload; the demo and exporter do not run it. Exact generation and receipt definitions are in [PROTOCOL.md](PROTOCOL.md) and [evaluation-contract.json](evaluation-contract.json).

The fixed evaluation completed once, including its full deterministic repeat: 100 measurements and all 22 integrity checks passed. [Complete results](results/evaluation.md) and [machine-readable export](results/evaluation.json) retain every seed score and pooled bin. The exporter consumed the saved receipt without rerunning scoring.

| Transform | Mean Brier | Mean log loss | Mean seed ECE | Pooled ECE |
| --- | --- | --- | --- | --- |
| oracle | 0.163667 | 0.497115 | 0.038333 | 0.018333 |
| shrink | 0.186208 | 0.559996 | 0.130000 | 0.130000 |
| expand | 0.169982 | 0.566385 | 0.086000 | 0.076000 |
| reversed | 0.501333 | 1.434403 | 0.505000 | 0.505000 |

This overview rounds derived values to six decimals; the export retains full precision. Oracle had the lowest mean Brier and log loss among these four fixed transforms in this synthetic run. This is a descriptive observation, not a general model-superiority claim. The complete report includes sample standard deviations across three seeds, all 48 seed scores and all 16 pooled reliability rows. Mean calibration gap is approximately 0.025 for each transform despite the different bin errors.

Execution used Python 3.14.7 on macOS ARM64. Measured CPU before final receipt/database closeout was 0.087661 seconds; the conservative charge was the full 60-second reservation. Recorded runner wall time was 0.104439 seconds and conservative combined peak memory was 60,735,488 bytes. These are operational measurements, not hard whole-operation containment. The workload had one compute thread and one supervisor thread. Both source and installed-package tests passed on the recorded interpreter; older supported Python versions were not tested.

## Receipt-only export

```sh
PYTHONPATH=src python3 -m probability_calibration_auditor.export receipt.json \
  --receipt-sha256 RECEIPT_SHA256 \
  --source-sha256 CORE_SOURCE_SHA256 \
  --runner-sha256 RUNNER_SHA256 > evaluation.json
```

Supply lowercase 64-character digest pins. The exporter validates the private receipt and emits an explicit public allowlist. It never imports scoring code or regenerates outcomes. Caller-supplied digests do not authenticate a source by themselves or establish external operation completion. Review provenance separately.

The exported JSON retains all 48 first-pass seed scores and 48 pooled sufficient statistics, plus four accounting values. Derived seed summaries use sample standard deviation across only three seeds. Derived pooled ECE is generally different from mean per-seed ECE. `export.render_markdown(public_object)` produces complete tables from the public export alone.

## Offline packaging

The original PEP 517 backend uses only the standard library and declares no build dependencies. It writes a deterministic pure-Python wheel with SHA256 RECORD entries and the `probability-calibration-auditor` console script. Use an existing local toolchain without package-index access; no downloaded dependency is required.

One clean offline installation was independently verified in a fresh virtual environment using Python 3.14.7 and existing pip 26.2.1, with no package-index access or dependencies downloaded. Pip itself was not installed into that environment. Verification checked all 10 wheel members, all six installed package modules, and all 14 installed RECORD entries, including exact bytes and hashes. All 20 unchanged hand-oracle and invented-fixture tests passed against installed code outside the source directory.

Installed module demo, console demo, and console stdin checks produced identical output and passed the four-row hand oracle. The entry-point code ran through guarded `runpy` in the isolated environment. Console-script bytes, executable mode and shebang were verified; a separate operating-system shebang launch was not tested.

Verified wheel: `probability_calibration_auditor-0.1.0-py3-none-any.whl`

SHA256: `e6ee67e18407823c570bd2a5a55c51ffeaf266ce5c537ef00191f0347eed0795`

Installation measured 3.103096 CPU seconds before final receipt closeout and 3.269271 active wall seconds, with a conservative combined peak RSS of 114,900,992 bytes. CPU includes the supervisor and waited children, including read-only host samplers; RSS combines the parent peak and maximum sequential child peak. These operational observations exclude final persistence/database closeout and do not prove hard process-tree or memory containment.

Scientific code, tests, backend, protocol and evaluation results are byte-identical to the verified installation inputs. The subsequent change only documents those installation facts in this README. Evaluation and installation were not rerun for documentation.

## Scope

This is a small synthetic diagnostic study. Three seeds, coarse bins, paired outcomes and fixed transforms do not establish real-world calibration, fairness, or model superiority. No winning threshold is imposed. Report all outcomes and retain failed checks.

No license grant has been selected.
