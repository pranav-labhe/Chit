# Architecture

Atmini -> AtminiBridge -> ChitRuntime -> ChitModel
                          
                                                   |              |
                                                   |              +-- Transformer weights
                                                   +-- MemoryStore

Chit is the model/runtime component, not the whole Atmini system. Memory stays external so experiences do not require immediate retraining.
