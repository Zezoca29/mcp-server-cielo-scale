"""
Python AST Analyzer for MCP Orchestrator
Analyzes Python code and extracts functions, inputs, outputs, complexity, branches
"""

import ast
import sys
import json
from typing import List, Dict, Any, Set, Optional

class PythonCodeAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.functions = []
        self.current_function = None
        self.total_branches = 0
        self.complexity = 0
        self.side_effects = set()
        
    def analyze(self, code: str) -> Dict[str, Any]:
        """Analisa o código Python e retorna métricas estruturadas"""
        try:
            tree = ast.parse(code)
            self.visit(tree)
            
            return {
                "functions": self.functions,
                "inputs": self._collect_all_inputs(),
                "outputs": self._collect_all_outputs(), 
                "complexity": self.complexity,
                "branches": self.total_branches,
                "side_effects": list(self.side_effects)
            }
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}"}
        except Exception as e:
            return {"error": f"Analysis error: {e}"}
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visita definições de função"""
        func_info = {
            "name": node.name,
            "inputs": self._extract_function_inputs(node),
            "outputs": self._extract_function_outputs(node),
            "line_start": node.lineno,
            "line_end": node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
            "branches": 0,
            "local_complexity": 1  # Base complexity
        }
        
        # Salvar contexto atual
        prev_function = self.current_function
        self.current_function = func_info
        
        # Analisar corpo da função
        for stmt in node.body:
            self.visit(stmt)
            
        # Atualizar métricas da função
        func_info["branches"] = self.current_function["branches"] 
        func_info["local_complexity"] = self.current_function["local_complexity"]
        
        self.functions.append(func_info)
        self.total_branches += func_info["branches"]
        self.complexity += func_info["local_complexity"]
        
        # Restaurar contexto
        self.current_function = prev_function
        
        # Não visitar filhos automaticamente (já visitamos manualmente)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visita funções assíncronas"""
        self.visit_FunctionDef(node)  # Mesmo tratamento
        self.side_effects.add("async_operations")
    
    def visit_If(self, node: ast.If):
        """Conta branches condicionais"""
        if self.current_function:
            self.current_function["branches"] += 1
            self.current_function["local_complexity"] += 1
            
        self.generic_visit(node)
    
    def visit_For(self, node: ast.For):
        """Conta loops como branches"""
        if self.current_function:
            self.current_function["branches"] += 1
            self.current_function["local_complexity"] += 1
            
        self.generic_visit(node)
    
    def visit_While(self, node: ast.While):
        """Conta loops while"""
        if self.current_function:
            self.current_function["branches"] += 1
            self.current_function["local_complexity"] += 1
            
        self.generic_visit(node)
    
    def visit_Try(self, node: ast.Try):
        """Conta try/except como branches"""
        if self.current_function:
            # Try + cada except/else/finally
            branches_count = 1 + len(node.handlers)
            if node.orelse:
                branches_count += 1
            if node.finalbody:
                branches_count += 1
                
            self.current_function["branches"] += branches_count
            self.current_function["local_complexity"] += branches_count
            
        self.generic_visit(node)
    
    def visit_With(self, node: ast.With):
        """Context managers podem ter side effects"""
        self.side_effects.add("context_managers")
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        """Detecta chamadas que podem ter side effects"""
        # Heurísticas para detectar side effects
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in ['print', 'open', 'input', 'exec', 'eval']:
                self.side_effects.add("io_operations")
            elif func_name in ['setattr', 'delattr', 'globals', 'locals']:
                self.side_effects.add("state_modification")
                
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in ['write', 'read', 'append', 'close', 'flush']:
                self.side_effects.add("io_operations") 
            elif attr_name in ['send', 'get', 'post', 'put', 'delete']:
                self.side_effects.add("network_operations")
            elif attr_name in ['commit', 'rollback', 'execute']:
                self.side_effects.add("database_operations")
                
        self.generic_visit(node)
    
    def visit_Global(self, node: ast.Global):
        """Uso de variáveis globais"""
        self.side_effects.add("global_state")
        self.generic_visit(node)
        
    def visit_Nonlocal(self, node: ast.Nonlocal):
        """Uso de variáveis não-locais"""
        self.side_effects.add("nonlocal_state")
        self.generic_visit(node)
    
    def _extract_function_inputs(self, node: ast.FunctionDef) -> List[Dict[str, Any]]:
        """Extrai parâmetros da função"""
        inputs = []
        
        # Argumentos posicionais
        for arg in node.args.args:
            param = {
                "name": arg.arg,
                "type": self._get_annotation(arg.annotation) if arg.annotation else "Any",
                "kind": "positional"
            }
            inputs.append(param)
        
        # Argumentos *args
        if node.args.vararg:
            inputs.append({
                "name": f"*{node.args.vararg.arg}",
                "type": self._get_annotation(node.args.vararg.annotation) if node.args.vararg.annotation else "tuple",
                "kind": "varargs"
            })
            
        # Argumentos **kwargs
        if node.args.kwarg:
            inputs.append({
                "name": f"**{node.args.kwarg.arg}",
                "type": self._get_annotation(node.args.kwarg.annotation) if node.args.kwarg.annotation else "dict", 
                "kind": "kwargs"
            })
        
        # Keyword-only arguments
        for arg in node.args.kwonlyargs:
            param = {
                "name": arg.arg,
                "type": self._get_annotation(arg.annotation) if arg.annotation else "Any",
                "kind": "keyword_only"
            }
            inputs.append(param)
            
        return inputs
    
    def _extract_function_outputs(self, node: ast.FunctionDef) -> List[str]:
        """Extrai tipo de retorno da função"""
        outputs = []
        
        # Type annotation no return
        if node.returns:
            return_type = self._get_annotation(node.returns)
            outputs.append(return_type)
        else:
            # Tentar inferir do corpo da função
            return_types = set()
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and stmt.value:
                    inferred = self._infer_return_type(stmt.value)
                    if inferred:
                        return_types.add(inferred)
            
            outputs.extend(list(return_types) if return_types else ["Any"])
            
        return outputs
    
    def _get_annotation(self, annotation: Optional[ast.AST]) -> str:
        """Converte annotation AST para string"""
        if annotation is None:
            return "Any"
            
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value) 
        elif isinstance(annotation, ast.Attribute):
            return f"{self._get_annotation(annotation.value)}.{annotation.attr}"
        elif isinstance(annotation, ast.Subscript):
            value = self._get_annotation(annotation.value)
            slice_val = self._get_annotation(annotation.slice)
            return f"{value}[{slice_val}]"
        else:
            return "Complex"
    
    def _infer_return_type(self, return_value: ast.AST) -> Optional[str]:
        """Infere tipo de retorno baseado no valor"""
        if isinstance(return_value, ast.Constant):
            if isinstance(return_value.value, bool):
                return "bool"
            elif isinstance(return_value.value, int):
                return "int"
            elif isinstance(return_value.value, float):
                return "float"
            elif isinstance(return_value.value, str):
                return "str"
            elif return_value.value is None:
                return "None"
        elif isinstance(return_value, ast.List):
            return "list"
        elif isinstance(return_value, ast.Dict):
            return "dict"
        elif isinstance(return_value, ast.Tuple):
            return "tuple"
        elif isinstance(return_value, ast.Set):
            return "set"
            
        return None
    
    def _collect_all_inputs(self) -> List[str]:
        """Coleta todos os inputs de todas as funções"""
        all_inputs = []
        for func in self.functions:
            for inp in func["inputs"]:
                param_str = f"{inp['name']}: {inp['type']}"
                if param_str not in all_inputs:
                    all_inputs.append(param_str)
        return all_inputs
    
    def _collect_all_outputs(self) -> List[str]:
        """Coleta todos os outputs de todas as funções"""
        all_outputs = []
        for func in self.functions:
            for out in func["outputs"]:
                if out not in all_outputs:
                    all_outputs.append(out)
        return all_outputs

def main():
    """Entry point - lê código do stdin e imprime análise JSON"""
    try:
        # Ler código do stdin
        code = sys.stdin.read()
        if not code.strip():
            print(json.dumps({"error": "No code provided"}))
            return
        
        # Analisar código
        analyzer = PythonCodeAnalyzer()
        result = analyzer.analyze(code)
        
        # Imprimir resultado como JSON
        print(json.dumps(result, indent=None, separators=(',', ':')))
        
    except Exception as e:
        error_result = {"error": f"Analyzer failure: {str(e)}"}
        print(json.dumps(error_result))
        sys.exit(1)

if __name__ == "__main__":
    main()