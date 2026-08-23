# Architecture

`Webhook → event store (idempotent hash) → Payment → DetectionAgent → ML prediction/ranking → DecisionAgent → GuardrailEngine → approval → ExecutionAgent → verified OutcomeAgent → analytics/audit`.

The application is a modular FastAPI monolith. No LLM is on the authorization or execution path. Targets (`recovered`, `recovered_amount`) are deliberately absent from `ml.preprocessing.FEATURES`; they are outcomes only. The model artifacts retain training metadata and evaluation metrics.
