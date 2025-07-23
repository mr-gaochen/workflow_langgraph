# WorkFlow.py
import json
from typing import Dict, List, TypedDict, Any, Annotated, Callable, Literal, Optional, Union
import operator
import inspect

from langgraph.graph import StateGraph, END, START

from node_data import NodeData
from util import logger


# Tool registry to hold information about tools
tool_registry: Dict[str, Callable] = {}
tool_info_registry: Dict[str, str] = {}

# Decorator to register tools
def tool(func: Callable) -> Callable:
    signature = inspect.signature(func)
    docstring = func.__doc__ or ""
    tool_info = f"{func.__name__}{signature} - {docstring}"
    tool_registry[func.__name__] = func
    tool_info_registry[func.__name__] = tool_info
    return func


@tool
def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers"""
    return a + b

@tool
def format_result(value: int) -> str:
    """Format the result as a string"""
    return f"The result is: {value}"

# Subgraph registry to hold all the subgraph
subgraph_registry: Dict[str, Any] = {}

# Decorator to register tools
def tool(func: Callable) -> Callable:
    signature = inspect.signature(func)
    docstring = func.__doc__ or ""
    tool_info = f"{func.__name__}{signature} - {docstring}"
    tool_registry[func.__name__] = func
    tool_info_registry[func.__name__] = tool_info
    return func

def parse_nodes_from_json(graph_data: Dict[str, Any]) -> Dict[str, NodeData]:
    """
    Parses node data from a subgraph's JSON structure.

    Args:
        graph_data: A dictionary representing a subgraph.
    Returns:
        A dictionary of NodeData objects keyed by their unique IDs.
    """
    node_map = {}
    for node_data in graph_data.get("nodes", []):
        node = NodeData.from_dict(node_data)
        node_map[node.uniq_id] = node
    return node_map

def find_nodes_by_type(node_map: Dict[str, NodeData], node_type: str) -> List[NodeData]:
    return [node for node in node_map.values() if node.type == node_type]


class PipelineState(TypedDict):
    history: Annotated[str, operator.add]
    task: Annotated[str, operator.add]
    condition: Annotated[bool, lambda x, y: y]

def execute_step(name:str, state: PipelineState, prompt_template: str) -> PipelineState:
    logger(f"{name} is working...")
    return state

def execute_tool(name: str, state: PipelineState, prompt_template: str) -> PipelineState:
    logger(f"{name} is working...")
    return state

def condition_switch(name:str, state: PipelineState, prompt_template: str) -> PipelineState:
    logger(f"{name} is working...")
    return state

def info_add(name: str, state: PipelineState, information: str) -> PipelineState:
    logger(f"{name} is working...")
    return state


def sg_add(name:str, state: PipelineState, sg_name: str) -> PipelineState:
    logger(f"{name} is working, it is a subgraph node call {sg_name} ...")
    subgraph = subgraph_registry[sg_name]
    response = subgraph.invoke(
        PipelineState(
            history=state["history"],
            task=state["task"],
            condition=state["condition"]
        )
    )
    return state


def conditional_edge(state: PipelineState) -> Literal["True", "False"]:
    if state["condition"] in ["True", "true", True]:
            return "True"
    else:
        return "False"

def build_subgraph(node_map: Dict[str, NodeData]) -> StateGraph:
    # Create the StateGraph instance first
    subgraph = StateGraph(PipelineState)

    # Start node, only one start point
    start_node = find_nodes_by_type(node_map, "START")[0]
    logger(f"Start root ID: {start_node.uniq_id}")
    # Start node, only one start point
    start_node = find_nodes_by_type(node_map, "START")[0]
    logger(f"Start root ID: {start_node.uniq_id}")

    # Step nodes
    step_nodes = find_nodes_by_type(node_map, "STEP")
    for current_node in step_nodes:
        if current_node.tool:
            tool_info = tool_info_registry[current_node.tool]
            prompt_template = f"""
            history: {{history}}
            {current_node.description}
            Available tool: {tool_info}
            Based on Available tool, arguments in the json format:
            "function": "<func_name>", "args": [<arg1>, <arg2>, ...]

            next stage directly parse then run <func_name>(<arg1>,<arg2>, ...) make sure syntax is right json and align function siganture
            """
            subgraph.add_node(
                current_node.uniq_id,
                lambda state, template=prompt_template, name=current_node.name : execute_tool(name, state, template)
            )
        else:
            prompt_template=f"""
            history: {{history}}
            {current_node.description}
            you reply in the json format
            """
            subgraph.add_node(
                current_node.uniq_id,
                lambda state, template=prompt_template, name=current_node.name: execute_step(name, state, template)
            )

    # Add INFO nodes
    info_nodes = find_nodes_by_type(node_map, "INFO")
    for info_node in info_nodes:
        # INFO nodes just append predefined information to the state history
        subgraph.add_node(
            info_node.uniq_id,
            lambda state, template=info_node.description, name=info_node.name: info_add(name, state, template)
        )

    # Add SUBGRAPH nodes
    subgraph_nodes = find_nodes_by_type(node_map, "SUBGRAPH")
    for sg_node in subgraph_nodes:
        subgraph.add_node(
            sg_node.uniq_id,
            lambda state, name=sg_node.name, sg_name=sg_node.name: sg_add(name, state, sg_name)
        )

    # Edges
    # Find all next nodes from start_node
    next_node_ids = start_node.nexts
    next_nodes = [node_map[next_id] for next_id in next_node_ids]

    for next_node in next_nodes:
        logger(f"Next node ID: {next_node.uniq_id}, Type: {next_node.type}")
        subgraph.add_edge(START, next_node.uniq_id)

    # Find all next nodes from step_nodes
    for node in step_nodes + info_nodes + subgraph_nodes:
        next_nodes = [node_map[next_id] for next_id in node.nexts]

        for next_node in next_nodes:
            logger(f"{node.name} {node.uniq_id}'s next node: {next_node.name} {next_node.uniq_id}, Type: {next_node.type}")
            subgraph.add_edge(node.uniq_id, next_node.uniq_id)

    # Find all condition nodes
    condition_nodes = find_nodes_by_type(node_map, "CONDITION")
    for condition in condition_nodes:
        condition_template = f"""{condition.description}
        history: {{history}}, decide the condition result in the json format:
        "switch": True/False
        """
        subgraph.add_node(
            condition.uniq_id,
            lambda state, template=condition_template, name=condition.name: condition_switch(name, state, template)
        )

        logger(f"{condition.name} {condition.uniq_id}'s condition")
        logger(f"true will go {condition.true_next}")
        logger(f"false will go {condition.false_next}")
        subgraph.add_conditional_edges(
            condition.uniq_id,
            conditional_edge,
            {
                "True": condition.true_next if condition.true_next else END,
                "False": condition.false_next if condition.false_next else END
            }
        )
    return subgraph.compile()


class MainGraphState(TypedDict):
    input: Union[str, None]

def invoke_root(state: MainGraphState):
    subgraph = subgraph_registry["root"]
    response = subgraph.invoke(
        PipelineState(
            history="",
            task="",
            condition=False
        )
    )
    return  {"input": state["input"]}


def run_workflow_as_server():
    # Load subgraph data
    with open("workflow.json", 'r') as file:
        graphs = json.load(file)

    # Process each subgraph
    for graph in graphs:
        subgraph_name = graph.get("name")
        node_map = parse_nodes_from_json(graph)

        # Register the tool functions dynamically if has tool node, must before build graph
        for tool_node in find_nodes_by_type(node_map, "TOOL"):
            tool_code = f"{tool_node.description}"
            exec(tool_code, globals())


        subgraph = build_subgraph(node_map)
        subgraph_registry[subgraph_name] = subgraph


    # Main Graph
    main_graph = StateGraph(MainGraphState)
    main_graph.add_node("subgraph", invoke_root)
    main_graph.set_entry_point("subgraph")
    main_graph = main_graph.compile()


    # ==========================
    # Run
    # ==========================
    for state in main_graph.stream(
        {
            "input": "hello",
        }
    ):
        logger(state)



if __name__ == "__main__":
    run_workflow_as_server()
