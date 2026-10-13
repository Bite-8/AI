# Predictive-error extrapolation hypothesis v1

Status: preregistered; not implemented and not evaluated.

This decision record fixes the first Mark2 computational-neuroscience hypothesis before variant code or results exist. It does not claim that a transformer layer is a cortical area, or that a residual-stream difference is a measured neural prediction-error signal. The experiment tests only the deliberately narrow computational analogy defined below.

## Decision

Adopt one principle from hierarchical predictive coding: a representation is updated in the direction of a residual error between an available state and its prediction. Rao and Ballard's original model sends higher-level predictions toward lower levels, carries residual errors forward, and iteratively changes internal representations to reduce those errors. Their simulation concerned visual cortex and learned receptive fields; it did not study language models.

For this experiment, two successive frozen decoder states are treated as an operational state/prediction pair. If `h31` is the output of zero-based decoder layer 30 and `h32` is the output of layer 31, the last layer's update `e = h32 - h31` is treated as an error-like direction. The variant applies exactly one fixed extrapolation before the model's final RMS normalization:

```text
h32_variant = h32 + beta * (h32 - h31)
beta = 0.10
```

The hypothesis is that a small continuation along the final learned update direction sharpens already-computed task evidence enough to increase exact-match MMLU accuracy. This is falsifiable: the existing paired decision rule can classify the intervention as supported, regressed, or inconclusive. The difference vector is not asserted to be the biological prediction error, and the operation does not recreate top-down cortical feedback, iterative inference, or learning.

## Primary evidence and architecture sources

- Rao, R. P. N. and Ballard, D. H. (1999), [Predictive coding in the visual cortex: a functional interpretation of some extra-classical receptive-field effects](https://doi.org/10.1038/4580). This is the primary computational model supporting prediction, residual-error transmission, and representation update.
- The pinned [Qwen3.5-9B `config.json`](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/config.json) fixes 32 text decoder layers, hidden size 4096, and the hybrid layer types used by the baseline.
- The pinned runtime's [Transformers v5.17.0 Qwen3.5 implementation](https://github.com/huggingface/transformers/blob/v5.17.0/src/transformers/models/qwen3_5/modeling_qwen3_5.py) defines `Qwen3_5TextModel.layers`, followed by `Qwen3_5TextModel.norm`, and each decoder layer's residual output. These are implementation facts, not neuroscience evidence.

## Why this principle was selected

The prediction/residual/update decomposition is explicit enough to state as inputs, state, update, and output. It permits a single frozen-weight intervention with no training, dataset change, extra model forward, or extra decoding branch. It is therefore directly testable under the existing Qwen3.5-9B, MMLU, greedy-decoding, and single-L4 contracts.

The main alternatives were not selected:

- Divisive normalization has strong neural and computational precedent, but Qwen3.5 already applies learned RMS normalizations throughout the stack. A new cross-feature normalization would confound the proposed biological principle with a second choice about axes and scale restoration.
- A recurrent predictive-coding loop would more closely resemble iterative inference, but it introduces a stopping rule and multiple forward passes. That is a separate resource and algorithmic decision rather than one isolated intervention.
- Neuromodulatory gain control would require an additional choice of uncertainty signal and gain schedule, making the first experiment depend on two coupled design decisions.

## Exact intervention boundary

The later implementation must locate the text model through the loaded `Qwen3_5ForConditionalGeneration` and require the pinned topology before installing any hooks or running generation:

- `config.text_config.num_hidden_layers == 32` and `hidden_size == 4096`;
- text decoder modules expose `layers[30]`, `layers[31]`, and the final `norm` in that order;
- each selected layer returns a floating tensor shaped `[batch, sequence, 4096]` (whether returned directly or as the documented first tuple element).

For every model-forward invocation, capture the output from `layers[30]` as `h31`. When `layers[31]` produces `h32`, replace only its hidden-state tensor with `h32 + 0.10 * (h32 - h31)`. Preserve any other return fields byte-for-byte and pass the replacement into the existing final `norm`, language-model head, cache handling, and generation path. Apply the same rule to the prompt prefill and every cached decoding step. Do not modify stored weights or either layer's internal attention, Gated DeltaNet, MLP, residual, or cache computation.

The one independent variable is whether this fixed rule is enabled: baseline is the unmodified output (`beta = 0`), variant is `beta = 0.10`. Beta tuning, layer selection, adaptive scaling, clipping, and normalization are not part of this experiment.

## Conditions held fixed

All values in `mark2/configs/qwen35_9b_mmlu.json`, the pinned model and dataset revisions, selected 100 questions and order, prompt/chat template, disabled thinking, BF16 unquantized weights, greedy decoding, seed, token limits, answer parser, metric, host profile, dependency pins, and artifact/qualification rules remain identical. Baseline and variant each require two eligible runs carrying the same experiment contract. No training or calibration examples are allowed.

## Normal behavior, invariants, and fail-closed behavior

Normal behavior produces exactly one replacement tensor per decoder invocation and leaves shape, dtype, device, sequence length, batch size, cache objects, and non-hidden return values unchanged. The implementation must not mutate `h31` or `h32` in place. It must remove hooks after a run, including exceptional exits.

Before generation, fail closed if the model class, config, module path, layer count, hidden size, or final-normalization ordering does not match the pinned boundary. During generation, fail closed before producing a prediction if either hook is missing or called out of order, a layer is called more than once for one decoder invocation, shapes/dtypes/devices differ, a tensor is non-floating or non-finite, the output container cannot be preserved, or the extrapolated tensor is non-finite. Do not silently fall back to baseline, select neighboring layers, cast types, clip values, disable the cache, or retry with a changed beta.

## Resource budget

The intervention adds zero model-forward calls and no model parameters. At the maximum 2,048-token input, one BF16 `[1, 2048, 4096]` retained activation is 16 MiB. Allowing the saved tensor, subtraction/addition temporaries, allocator effects, and the shorter decode steps, the preregistered limit is at most 128 MiB additional peak allocated GPU memory relative to a same-commit baseline run. End-to-end variant generation time must be at most 1.10 times the mean of the two eligible baseline runs. Exceeding either limit invalidates the variant implementation for this hypothesis rather than authorizing offload, quantization, shorter inputs, or a different host.

This budget is expected to fit the existing L4 24 GB profile because weights, cache policy, and forward count do not change and the upper bound is below one percent of 22,500 MiB usable VRAM. It remains an estimate until measured on the approved host; an OOM or budget breach is a failed implementation condition, not evidence about the hypothesis.

## Preregistered contract cross-reference

The machine-readable source is [`predictive_error_extrapolation_v1.json`](../../mark2/configs/predictive_error_extrapolation_v1.json). The table is intentionally checked by offline tests so a document/contract mismatch fails CI.

| contract field | preregistered value |
|---|---|
| `experiment_id` | `predictive-error-extrapolation-qwen35-9b-mmlu-v1` |
| `hypothesis_id` | `predictive-error-extrapolation-improves-mmlu-v1` |
| `independent_variable.id` | `final-layer-prediction-error-extrapolation-beta-0.10` |
| `primary_metric.name` | `exact_match_accuracy` |
| `primary_metric.direction` | `increase` |
| `decision_rule.minimum_accuracy_difference` | `0.05` |
| `decision_rule.significance_level` | `0.05` |
| `decision_rule.paired_test` | `exact-binomial-discordant-one-sided` |
| `decision_rule.require_identical_variant_predictions` | `true` |

The minimum effect is fixed at five correct answers out of 100 (5 percentage points), rather than treating the benchmark's 1-point resolution as meaningful improvement. Alpha is fixed at 0.05. The effect threshold and exact paired significance gate are both required independently: for example, five variant-only discordances and no baseline-only discordance yield one-sided `p = 1/32 = 0.03125`, while a 5-point net gain with more mixed discordances can remain inconclusive. Each of the two paired comparisons must independently pass both gates, and the two variant prediction sequences must be identical. Runs are never pooled to manufacture significance.

## Interpretation and stopping rules

- `supported`: both eligible paired comparisons meet the positive 0.05 accuracy difference and improvement `p <= 0.05` requirements.
- `regressed`: both meet the symmetric negative effect and worsening significance requirements implemented by the existing evaluator.
- `inconclusive`: every other eligible outcome, including disagreement between pairs.

Reject or revise this hypothesis after a valid `regressed` result. Treat `inconclusive` as insufficient evidence; do not tune beta, layers, thresholds, or prompts against these 100 outcomes under this experiment ID. Any later sensitivity study requires a new preregistration derived after this experiment is closed. Implementation failure, ineligible artifacts, resource-budget failure, or baseline ineligibility is operational failure and must not be classified as scientific support or rejection.
