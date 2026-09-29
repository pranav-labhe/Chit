# Architecture

Atmini -> AtminiBridge -> MatiRuntime -> MatiModel
                         |              |
                         |              +-- Transformer weights
                         +-- MemoryStore

Mati is the model/runtime component, not the whole Atmini system. Memory stays external so experiences do not require immediate retraining.
