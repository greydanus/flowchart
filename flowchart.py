import ast
import json
import argparse
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional

@dataclass
class Literal:
    name: str
    is_positive: bool = True

class DNFConverter:
    def convert(self, node: ast.expr) -> List[List[Literal]]:
        if isinstance(node, ast.Name):
            return [[Literal(node.id)]]
            
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            if isinstance(node.operand, ast.Name):
                return [[Literal(node.operand.id, False)]]
            inner_dnf = self.convert(node.operand)
            return self._negate_dnf(inner_dnf)
            
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = [[]]
                for value in node.values:
                    terms = self.convert(value)
                    result = self._distribute_and(result, terms)
                return result
                
            if isinstance(node.op, ast.Or):
                result = []
                for value in node.values:
                    result.extend(self.convert(value))
                return result
                
        return []
        
    def _negate_dnf(self, terms: List[List[Literal]]) -> List[List[Literal]]:
        if not terms:
            return []
        result = [[Literal(terms[0][0].name, not terms[0][0].is_positive)]]
        for term in terms[0][1:]:
            result = self._distribute_and(result, [[Literal(term.name, not term.is_positive)]])
        return result
        
    def _distribute_and(self, terms1: List[List[Literal]], terms2: List[List[Literal]]) -> List[List[Literal]]:
        result = []
        for t1 in terms1:
            for t2 in terms2:
                result.append(t1 + t2)
        return result

class GraphBuilder:
    def __init__(self, questions: Dict[str, str]):
        self.questions = questions
        self.nodes: Set[str] = set()
        self.edges: Set[Tuple[str, str, str]] = set()
        self.node_count: Dict[str, int] = {}
        
    def build_mermaid(self, terms: List[List[Literal]]) -> str:
        lines = [
            "%%{init: {'flowchart': {'rankSpacing': 25, 'nodeSpacing': 50, 'padding': 5}}}%%",
            "flowchart TD"
        ]
        
        lines.append('Start["Start"]')
        
        start_questions = set(term[0].name for term in terms)
        
        for term in terms:
            self._add_term(term)
            
        for node in self.nodes:
            base_name = node.split('_')[0]
            lines.append(f'{node}["{self.questions.get(base_name, base_name)}"]')
        
        lines.append('Approve["Yes"]')
        lines.append('Deny["No"]')
        
        for start_q in start_questions:
            lines.append(f"Start --> {start_q}")
        
        for src, cond, tgt in self.edges:
            lines.append(f"{src} -->|{cond}| {tgt}")
            
        lines.extend([
            "classDef default fill:#f0f0f0,stroke:#333,stroke-width:1px,color:black",
            "classDef start fill:#FFA500,stroke:#333,color:white",
            "classDef approval fill:#4CAF50,stroke:#333,color:white",
            "classDef rejection fill:#DC143C,stroke:#333,color:white",
            "class Start start",
            "class Approve approval",
            "class Deny rejection",
            "linkStyle default stroke:#333,stroke-width:2px"
        ])
        
        return "\n".join(lines)

    def build_dag(self, terms: List[List[Literal]]) -> Dict:
        dag = {"nodes": {}, "edges": {}, "terminal_nodes": {"Approve": "Yes", "Deny": "No"}}
        
        start_questions = set(term[0].name for term in terms)
        
        dag["nodes"]["Start"] = "Decision Point"
        
        for node in self.nodes:
            base_name = node.split('_')[0]
            dag["nodes"][base_name] = self.questions.get(base_name, base_name)
        
        for term in terms:
            self._add_term(term)
        
        dag["edges"]["Start"] = {
            "Start": list(start_questions)
        }
        
        for src, cond, tgt in self.edges:
            base_src = src.split('_')[0]
            base_tgt = tgt.split('_')[0]
            
            if base_src not in dag["edges"]:
                dag["edges"][base_src] = {}
            
            dag["edges"][base_src][cond] = [base_tgt]
        
        return dag
        
    def _add_term(self, term: List[Literal]) -> None:
        if not term:
            return
            
        prev_node = None
        for i, lit in enumerate(term):
            curr_count = self.node_count.get(lit.name, 0)
            self.node_count[lit.name] = curr_count + 1
            curr_node = f"{lit.name}_{curr_count}" if curr_count > 0 else lit.name
            self.nodes.add(curr_node)
            
            if prev_node:
                yes_target = curr_node if is_prev_positive else "Deny"
                no_target = "Deny" if is_prev_positive else curr_node
                self.edges.add((prev_node, "Yes", yes_target))
                self.edges.add((prev_node, "No", no_target))
                
            if i == len(term) - 1:
                yes_target = "Approve" if lit.is_positive else "Deny"
                no_target = "Deny" if lit.is_positive else "Approve"
                self.edges.add((curr_node, "Yes", yes_target))
                self.edges.add((curr_node, "No", no_target))
                
            prev_node = curr_node
            is_prev_positive = lit.is_positive

def build_graph(data: Dict[str, str], use_dag: bool = False) -> str:
    # Extract logic and questions from the input dictionary
    logic = data.get('logic', '')
    questions = {k: v for k, v in data.items() if k != 'logic'}
    
    node = ast.parse(logic, mode='eval').body
    terms = DNFConverter().convert(node)
    builder = GraphBuilder(questions)
    return json.dumps(builder.build_dag(terms), separators=(',', ':')) if use_dag else builder.build_mermaid(terms)

def main():
    default_data = {
        "Q1": "Are those Senate weaklings plotting against me?",
        "Q2": "Do my soldiers worship me completely?", 
        "Q3": "Is political reconciliation impossible?",
        "Q4": "Can Pompey's pathetic legions stop my genius?",
        "Q5": "Will crossing divide my supporters?",
        "logic": "(Q1 and not (Q5 and Q4)) or (Q2 and Q3)"
    }

    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str, help='JSON string containing questions and logic')
    parser.add_argument('--dag', action='store_true', help='Output as DAG JSON')
    args = parser.parse_args()
    
    data = json.loads(args.data) if args.data else default_data
    
    print(build_graph(data, args.dag))

if __name__ == "__main__":
    main()