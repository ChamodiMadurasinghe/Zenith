"""Shared LangChain tool-calling agent loop."""

from __future__ import annotations

from typing import Any


def tool_trace(intermediate_steps: list) -> list[dict[str, Any]]:
    trace = []
    for step in intermediate_steps or []:
        try:
            action, observation = step
            trace.append(
                {
                    "tool": getattr(action, "tool", None),
                    "input": getattr(action, "tool_input", None),
                    "observation": str(observation)[:2000],
                }
            )
        except Exception:
            continue
    return trace


def run_tool_agent(
    *,
    llm,
    tools: list,
    system_prompt: str,
    user_message: str,
    chat_history: list | None = None,
    max_iterations: int = 8,
) -> dict:
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system_prompt}"),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        max_iterations=max_iterations,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
    )

    history_msgs = []
    for turn in chat_history or []:
        role = (turn.get("role") or "").lower()
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            history_msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            history_msgs.append(AIMessage(content=content))

    result = executor.invoke(
        {
            "input": user_message,
            "chat_history": history_msgs[-8:],
            "system_prompt": system_prompt,
        }
    )
    return {
        "output": (result.get("output") or "").strip(),
        "intermediate_steps": result.get("intermediate_steps") or [],
        "tool_trace": tool_trace(result.get("intermediate_steps") or []),
    }
