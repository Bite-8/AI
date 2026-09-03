# Experiment: `<ID> <short title>`

> このファイルをコピーし、`experiments/<ID>-<slug>.md`として使用する。実行前に「事前登録」までをcommitし、実行後に結果と判断を追記する。

## Metadata

- Status: planned / running / completed / rejected
- Owner:
- Created / completed:
- Baseline repository + commit/model revision:
- Experiment code commit:
- Related principle matrix row:

## Question and hypothesis

- **Question**:
- **Observation from neuroscience**:
- **Computational interpretation**:
- **Difference from existing AI mechanism**:
- **Hypothesis**: If `<single change>`, then `<metric>` improves because `<mechanism>`.
- **Null/alternative explanations**:

## Preregistration (実行前に固定)

- Independent variable (一つ):
- Controlled variables:
- Primary metric:
- Secondary metrics:
- Resource metrics (time / peak memory / FLOPs or proxy):
- Dataset / version / split:
- Seeds:
- Success threshold:
- Rejection threshold:
- Stop condition / resource budget:

## Implementation

- Minimal change:
- Baseline path remains runnable:
- Configuration / command:
- Environment and hardware:
- Expected artifacts:

## Results（実行後に追記）

| Variant | Seed | Primary | Secondary | Time | Peak memory | Notes |
|---|---:|---:|---:|---:|---:|---|
| baseline | — | — | — | — | — | — |
| intervention | — | — | — | — | — | — |

再現コマンドとraw artifactへの相対パス:

```bash
# command
```

## Analysis and decision

- Uncertainty / variance:
- Confounders / failures:
- Result: supported / inconclusive / contradicted
- Decision: keep / revise / discard
- Why:
- Next smallest experiment:
