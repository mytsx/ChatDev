"""Loop counter guard node executor."""

from typing import List, Dict, Any

from entity.configs import Node
from entity.configs.node.loop_counter import LoopCounterConfig
from entity.messages import Message, MessageRole
from runtime.node.executor.base import NodeExecutor


# Prefix added to the exhaustion message so downstream edges can
# distinguish "loop continues" from "loop exhausted".
LOOP_EXIT_MARKER = "LOOP_EXIT"


class LoopCounterNodeExecutor(NodeExecutor):
    """Track loop iterations and route based on exhaustion state.

    * **Not exhausted** – passes input messages through unchanged so the
      "continue loop" edge can fire.
    * **Exhausted** – emits a message prefixed with ``LOOP_EXIT`` so the
      "exit loop" edge can fire.

    Downstream edges should use keyword conditions to differentiate:
    * Continue edge: ``none: [LOOP_EXIT]``
    * Exit edge:     ``any:  [LOOP_EXIT]``
    """

    STATE_KEY = "loop_counter"

    def execute(self, node: Node, inputs: List[Message]) -> List[Message]:
        config = node.as_config(LoopCounterConfig)
        if config is None:
            raise ValueError(f"Node {node.id} missing loop_counter configuration")

        state = self._get_state()
        counter = state.setdefault(node.id, {"count": 0})
        counter["count"] += 1
        count = counter["count"]

        if count < config.max_iterations:
            self.log_manager.debug(
                f"LoopCounter {node.id}: iteration {count}/{config.max_iterations} (pass-through)"
            )
            # Pass input through so the "continue" edge fires.
            return list(inputs) if inputs else []

        # --- Exhausted ---
        if config.reset_on_emit:
            counter["count"] = 0

        raw_message = config.message or f"Loop limit reached ({config.max_iterations})"
        content = f"{LOOP_EXIT_MARKER}: {raw_message}"
        metadata = {
            "loop_counter": {
                "count": count,
                "max": config.max_iterations,
                "reset_on_emit": config.reset_on_emit,
            }
        }

        self.log_manager.debug(
            f"LoopCounter {node.id}: iteration {count}/{config.max_iterations}"
            " reached limit, releasing output"
        )

        return [Message(
            role=MessageRole.ASSISTANT,
            content=content,
            metadata=metadata,
        )]

    def _get_state(self) -> Dict[str, Dict[str, Any]]:
        return self.context.global_state.setdefault(self.STATE_KEY, {})
