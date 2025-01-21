import ast, json, argparse
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional

@dataclass
class Literal:
    name: str
    is_positive: bool = True

class NegationNormalizer:
    def __init__(self):
        self.negated_nodes = set()
        
    def normalize(self, node: ast.expr) -> ast.expr:
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            if isinstance(node.operand, ast.Name):
                self.negated_nodes.add(node.operand.id)
                return node.operand
            elif isinstance(node.operand, ast.BoolOp):
                new_op = ast.Or() if isinstance(node.operand.op, ast.And) else ast.And()
                node.operand.op = new_op
                node.operand.values = [ast.UnaryOp(op=ast.Not(), operand=val) for val in node.operand.values]
                return self.normalize(node.operand)
        elif isinstance(node, ast.BoolOp):
            node.values = [self.normalize(value) for value in node.values]
        return node

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
        negated_terms = []
        for term in terms:
            result = [[Literal(term[0].name, not term[0].is_positive)]]
            for lit in term[1:]:
                result = self._distribute_and(result, [[Literal(lit.name, not lit.is_positive)]])
            negated_terms.extend(result)
        return negated_terms
        
    def _distribute_and(self, terms1: List[List[Literal]], terms2: List[List[Literal]]) -> List[List[Literal]]:
        result = []
        for t1 in terms1:
            for t2 in terms2:
                result.append(t1 + t2)
        return result

class LogicPreprocessor:
    def __init__(self):
        self.next_id = 1
        self.split_map = {}
        
    def get_next_id(self):
        id = f"V{self.next_id}"
        self.next_id += 1
        return id
        
    def find_or_groups(self, node, depth=0):
        if depth >= 4:
            return []
        if not isinstance(node, ast.BoolOp):
            return []
        groups = []
        if isinstance(node.op, ast.And):
            for i, val in enumerate(node.values):
                if isinstance(val, ast.BoolOp) and isinstance(val.op, ast.Or):
                    or_terms = []
                    for or_val in val.values:
                        if isinstance(or_val, ast.Name):
                            or_terms.append(or_val.id)
                        elif isinstance(or_val, ast.UnaryOp) and isinstance(or_val.operand, ast.Name):
                            or_terms.append(or_val.operand.id)
                    if or_terms:
                        remaining_terms = node.values[:i] + node.values[i+1:]
                        groups.append((or_terms, remaining_terms))
                groups.extend(self.find_or_groups(val, depth + 1))
        return groups
        
    def preprocess(self, data):
        logic = data.get('logic', '')
        questions = {k: v for k, v in data.items() if k != 'logic'}
        try:
            parts = logic.split(' and ')
            or_parts = [p for p in parts if ' or ' in p]
            other_parts = [p for p in parts if ' or ' not in p]
            logic = ' and '.join(or_parts + other_parts)
            node = ast.parse(logic, mode='eval').body
            or_groups = self.find_or_groups(node)
            if not or_groups:
                return data, {}
            new_questions = questions.copy()
            new_logic = logic
            for or_terms, _ in or_groups:
                virtual_node = self.get_next_id()
                self.split_map[virtual_node] = or_terms
                or_desc = " OR ".join(questions[t] for t in or_terms if t in questions)
                new_questions[virtual_node] = f"Does patient meet either:\n{or_desc}?"
                old_part = "(" + " or ".join(or_terms) + ")"
                new_logic = new_logic.replace(old_part, virtual_node)
            return {**new_questions, 'logic': new_logic}, self.split_map
        except:
            return data, {}

class GraphBuilder:
    def __init__(self, questions: Dict[str, str], split_map: Dict[str, List[str]] = None, negated_nodes: Set[str] = None):
        self.questions = questions
        self.nodes = set()
        self.edges = set()
        self.node_count = {}
        self.split_map = split_map or {}
        self.negated_nodes = negated_nodes or set()
        
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
            if start_q in self.split_map:
                lines.append(f'{start_q}["{self.questions.get(start_q, start_q)}"]')
                for q in self.split_map[start_q]:
                    lines.append(f"Start --> {q}")
                    lines.append(f'{q}["{self.questions.get(q, q)}"]')
                    lines.append(f"{q} -->|Yes| {start_q}")
                    lines.append(f"{q} -->|No| Deny")
            else:
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
        dag["edges"]["Start"] = {"Start": list(start_questions)}
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
            curr_node = lit.name
            if curr_node in self.node_count:
                existing_edges = {e[0] for e in self.edges if e[2] == curr_node} | {e[2] for e in self.edges if e[0] == curr_node}
                if existing_edges:
                    self.node_count[curr_node] += 1
                    curr_node = f"{curr_node}_{self.node_count[curr_node]}"
            else:
                self.node_count[curr_node] = 0
            self.nodes.add(curr_node)
            
            is_negated = curr_node in self.negated_nodes
            if prev_node:
                yes_target = curr_node if (is_prev_positive != is_negated) else "Deny"
                no_target = "Deny" if (is_prev_positive != is_negated) else curr_node
                self.edges.add((prev_node, "Yes", yes_target))
                self.edges.add((prev_node, "No", no_target))
            if i == len(term) - 1:
                yes_target = "Approve" if (lit.is_positive != is_negated) else "Deny"
                no_target = "Deny" if (lit.is_positive != is_negated) else "Approve"
                self.edges.add((curr_node, "Yes", yes_target))
                self.edges.add((curr_node, "No", no_target))
            prev_node = curr_node
            is_prev_positive = lit.is_positive

def build_graph(data: Dict[str, str], use_dag: bool = False) -> str:
    preprocessed, split_map = LogicPreprocessor().preprocess(data)
    logic = preprocessed.get('logic', '')
    questions = {k: v for k, v in preprocessed.items() if k != 'logic'}
    
    normalizer = NegationNormalizer()
    node = ast.parse(logic, mode='eval').body
    normalized_node = normalizer.normalize(node)
    
    terms = DNFConverter().convert(normalized_node)
    builder = GraphBuilder(questions, split_map, normalizer.negated_nodes)
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